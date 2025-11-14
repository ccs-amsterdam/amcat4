from datetime import UTC, datetime, timedelta
from typing import Tuple

from amcat4.elastic import es
from amcat4.elastic.util import BulkInsertAction, batched_index_scan, es_bulk_create, es_bulk_upsert
from amcat4.models import AllowedContentType, IndexId, ObjectStorage, RegisterObject
from amcat4.objectstorage.s3bucket import PRESIGNED_POST_HOURS_VALID, scan_s3_objects
from amcat4.systemdata.fields import get_field
from amcat4.systemdata.versions import objectstorage_index_id, objectstorage_index_name

INFER_MIME_TYPE: dict[str, AllowedContentType] = {
    # Images (Inert/Pixel-based)
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    # Videos
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "webm": "video/webm",
    # Audio
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "m4a": "audio/m4a",
}


def register_objects(
    index: IndexId, field: str, objects: list[RegisterObject], max_bytes: int
) -> Tuple[int, list[ObjectStorage]]:
    """
    Register a list of ObjectStorage objects in ES. Returns an iterable of the newly registered objects.

    If force is False, only register objects that are new or have a different size than the
    existing object in ES. This is the usual behavior to avoid unnecessary updates. Use force
    for the (unlikely) case that you need to upload a different file to a filename that happens
    to have the same size as the existing file.
    """
    existing = _get_current(index, field, objects)
    new_total_size = _get_total_size(index)

    add_objects: dict[str, ObjectStorage] = {}
    for obj in objects:
        id = objectstorage_index_id(index, field, obj.filepath)

        existing_size = existing.get(id)
        if existing_size == obj.size and not obj.force:
            continue
        new_total_size += obj.size - (existing_size or 0)

        if new_total_size > max_bytes:
            raise ValueError(f"Total size of object storage exceeds maximum allowed size of {max_bytes} bytes.")

        obj = _create_object_doc(index, field, obj)
        add_objects[id] = obj

    _raise_if_invalid_type(index, field, add_objects)

    def generator():
        for id, obj in add_objects.items():
            yield BulkInsertAction(index=objectstorage_index_name(), id=id, doc=obj.model_dump())

    es_bulk_create(generator(), overwrite=True)

    return new_total_size, list(add_objects.values())


def get_object(index: IndexId, field: str, filepath: str) -> ObjectStorage | None:
    id = objectstorage_index_id(index, field, filepath)
    doc = es().options(ignore_status=[404]).get(index=objectstorage_index_name(), id=id)
    if not doc["found"]:
        return None
    return ObjectStorage.model_validate(doc["_source"])


def list_objects(
    index: IndexId,
    page_size: int = 1000,
    directory: str | None = None,
    search: str | None = None,
    recursive: bool = False,
    scroll_id: str | None = None,
) -> Tuple[str | None, list[ObjectStorage]]:
    query = {
        "bool": {
            "must": [
                {"term": {"index": index}},
            ]
        }
    }

    if directory:
        if recursive:
            query["bool"]["must"].append({"term": {"path": directory.strip("/")}})
        else:
            query["bool"]["must"].append({"prefix": {"filepath": directory.strip("/") + "/"}})
    else:
        if recursive:
            query["bool"]["must"].append({"term": {"path": ""}})

    if search:
        query["bool"]["must"].append({"wildcard": {"filepath": f"*{search}*"}})

    new_scroll_id, batch = batched_index_scan(
        index=objectstorage_index_name(), query=query, batchsize=page_size, scroll_id=scroll_id
    )

    return new_scroll_id, [ObjectStorage.model_validate(doc) for id, doc in batch]


def refresh_objectstorage(
    bucket: str,
    index: IndexId,
    field: str | None = None,
) -> dict:
    sync_time = datetime.now(UTC)

    prefix = f"{index}/"
    if field:
        prefix += f"{field}/"

    ## First, we bulk upsert everything from S3 to ES. Adding the sync time,
    ## and also creating the document if it doesn't exist yet.
    def gen():
        for obj in scan_s3_objects(bucket, prefix):
            index, field, filepath = obj["key"].split("/", 2)
            path, _, _ = split_filepath(filepath)

            action = BulkInsertAction(
                index=objectstorage_index_name(),
                id=objectstorage_index_id(index, field, filepath),
                doc={
                    "index": index,
                    "field": field,
                    "filepath": filepath,
                    "path": path,
                    "size": obj["size"],
                    "last_synced": sync_time,
                },
            )
            yield action

    es_bulk_upsert(gen(), batchsize=2500)

    return _clean_register(index, field=field, min_sync=sync_time)


def delete_register(index: IndexId, field: str | None = None):
    """
    Delete all ObjectStorage entries from ES for the given index and optional field.
    """
    query: dict = {
        "bool": {
            "must": [
                {"term": {"index": index}},
            ]
        }
    }
    if field:
        query["bool"]["must"].append({"term": {"field": field}})

    result = es().delete_by_query(index=objectstorage_index_name(), query=query)
    return dict(updated=result["deleted"], total=result["total"])


def delete_objects(index: IndexId, field: str, filepaths: list[str]):
    ids = [objectstorage_index_id(index, field, fp) for fp in filepaths]
    result = es().delete_by_query(index=objectstorage_index_name(), query={"ids": {"values": ids}}, refresh=True)
    print(result)
    return dict(updated=result["deleted"], total=result["total"])


def _clean_register(
    index: IndexId, field: str | None = None, min_sync: datetime | None = None, keep_pending: bool = True
) -> dict:
    """
    Remove all ObjectStorage entries from ES that were not synced since min_sync, or not synced at all if
    min_sync is None.

    If keep_pending is True, we do not delete entries for which the presigned post is still valid
    """
    query: dict = {
        "bool": {
            "must": [
                {"term": {"index": index}},
            ]
        }
    }

    if min_sync:
        query["bool"]["must"].append({"range": {"last_synced": {"gte": min_sync.isoformat()}}})
    else:
        query["bool"]["must"].append({"bool": {"must_not": {"exists": {"field": "last_synced"}}}})
    if field:
        query["bool"]["must"].append({"term": {"field": field}})

    if keep_pending:
        pending_time = datetime.now(UTC) - timedelta(hours=PRESIGNED_POST_HOURS_VALID + 1)
        query["bool"]["must"].append({"range": {"registered": {"lte": pending_time.isoformat()}}})

    result = es().delete_by_query(index=objectstorage_index_name(), query=query)
    return dict(updated=result["deleted"], total=result["total"])


def _get_current(index: IndexId, field: str, objects: list[RegisterObject]) -> dict[str, int]:
    """
    Given a list of ObjectStorage objects, get the current versions from ES.
    Existing objects will be returned in a dictionary with id as key and size as value;
    non-existing objects will be omitted.
    """
    ids = [objectstorage_index_id(index, field, obj.filepath) for obj in objects]
    res = es().options(ignore_status=[404]).mget(index=objectstorage_index_name(), ids=ids, source_includes=["size"])

    existing: dict[str, int] = dict()
    for doc in res["docs"]:
        if doc["found"]:
            existing[doc["_id"]] = doc["_source"]["size"]

    return existing


def _get_total_size(index: IndexId) -> int:
    query: dict = {"term": {"index": index}}

    agg = {"total_sum": {"sum": {"field": "size"}}}
    agg = es().search(query=query, index=objectstorage_index_name(), size=0, aggregations=agg)

    return agg["aggregations"]["total_sum"]["value"]


def _create_object_doc(index: IndexId, field: str, obj: RegisterObject) -> ObjectStorage:
    path, _, ext = split_filepath(obj.filepath)

    if obj.content_type is None:
        obj.content_type = INFER_MIME_TYPE.get(ext, None)
        if obj.content_type is None:
            raise ValueError(f"Cannot infer content type from file extension .{ext} for file {obj.filepath}")

    return ObjectStorage(
        index=index,
        field=field,
        filepath=obj.filepath,
        path=path,
        size=obj.size,
        content_type=obj.content_type,
        registered=datetime.now(UTC),
        last_synced=None,
    )


def split_filepath(filepath: str) -> Tuple[str, str, str]:
    if "/" in filepath:
        path, file = filepath.rsplit("/", 1)
    else:
        path, file = "", filepath

    ext = file.rsplit(".", 1)[-1].lower() if "." in file else ""
    return path, file, ext


def _raise_if_invalid_type(index: IndexId, field: str, objects: dict[str, ObjectStorage]) -> None:
    allowed_types = ["image", "video", "audio"]
    f = get_field(index, field)
    if not f:
        raise ValueError(f"Field {field} does not exist in index {index}")
    if f.type not in allowed_types:
        raise ValueError(f"Field {field} is of type {f.type}, which is not a valid multimedia type")

    for obj in objects.values():
        if not obj.content_type:
            raise ValueError(f"File {obj.filepath} has an unsupported file extension.")
        if not obj.content_type.startswith(f.type):
            raise ValueError(
                f"File {obj.filepath} with type {obj.content_type} cannot be uploaded for Field {obj.field} of type {f.type}."
            )
