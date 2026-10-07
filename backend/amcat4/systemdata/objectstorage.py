from datetime import UTC, datetime, timedelta
from typing import Any, Tuple

from amcat4.models import AllowedContentType, IndexId, ObjectStorage, RegisterObject
from amcat4.objectstorage.s3bucket import PRESIGNED_POST_HOURS_VALID, scan_s3_objects
from amcat4.postgres.connection import connection, execute, fetch_all, fetch_one
from amcat4.systemdata.fields import list_fields

_COLUMNS = "project_id AS index, field, filepath, path, size, content_type, registered, last_synced"

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


async def register_objects(
    index: IndexId, field: str, objects: list[RegisterObject], max_bytes: int
) -> Tuple[int, list[ObjectStorage]]:
    """
    Register a list of objects. Returns the new total size and the newly registered objects.

    Only objects that are new or have a different size than the existing object are registered, unless
    obj.force is set (for the unlikely case that you need to upload a different file to a filename that happens
    to have the same size as the existing file).
    """
    existing = await _get_current(index, field, objects)
    new_total_size = await _get_total_size(index)

    add_objects: dict[str, ObjectStorage] = {}
    for obj in objects:
        existing_size = existing.get(obj.filepath)
        if existing_size == obj.size and not obj.force:
            continue
        new_total_size += obj.size - (existing_size or 0)

        if new_total_size > max_bytes:
            raise ValueError(f"Total size of object storage exceeds maximum allowed size of {max_bytes} bytes.")

        add_objects[obj.filepath] = _create_object_doc(index, field, obj)

    await _raise_if_invalid_type(index, field, add_objects)

    if add_objects:
        async with connection() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(
                    """INSERT INTO object_storage (project_id, field, filepath, path, size, content_type, registered)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (project_id, field, filepath) DO UPDATE SET size = EXCLUDED.size,
                       content_type = EXCLUDED.content_type, registered = EXCLUDED.registered, last_synced = NULL""",
                    [
                        (o.index, o.field, o.filepath, o.path, o.size, o.content_type, o.registered)
                        for o in add_objects.values()
                    ],
                )

    return new_total_size, list(add_objects.values())


async def get_object(index: IndexId, field: str, filepath: str) -> ObjectStorage | None:
    row = await fetch_one(
        f"SELECT {_COLUMNS} FROM object_storage WHERE project_id = %s AND field = %s AND filepath = %s",  # type: ignore[arg-type]
        [index, field, filepath],
    )
    return ObjectStorage.model_validate(row) if row else None


async def list_objects(
    index: IndexId,
    page_size: int = 1000,
    directory: str | None = None,
    search: str | None = None,
    recursive: bool = False,
    scroll_id: str | None = None,
) -> Tuple[str | None, list[ObjectStorage]]:
    """
    List registered objects. Returns a scroll_id (pagination cursor, which also remembers the page size) and the
    objects. The scroll_id is None if there are no (more) objects.
    """
    conditions: list[str] = ["project_id = %s"]
    params: list[Any] = [index]
    if directory:
        if recursive:
            conditions.append("path = %s")
            params.append(directory.strip("/"))
        else:
            conditions.append("starts_with(filepath, %s)")
            params.append(directory.strip("/") + "/")
    elif recursive:
        conditions.append("path = ''")
    if search:
        conditions.append("strpos(filepath, %s) > 0")
        params.append(search)
    if scroll_id:
        size, field, filepath = scroll_id.split("/", 2)
        page_size = int(size)
        conditions.append("(field, filepath) > (%s, %s)")
        params += [field, filepath]

    rows = await fetch_all(
        f"SELECT {_COLUMNS} FROM object_storage WHERE {' AND '.join(conditions)} ORDER BY field, filepath LIMIT %s",  # type: ignore[arg-type]
        [*params, page_size],
    )
    objects = [ObjectStorage.model_validate(row) for row in rows]
    new_scroll_id = f"{page_size}/{objects[-1].field}/{objects[-1].filepath}" if objects else None
    return new_scroll_id, objects


async def refresh_objectstorage(
    bucket: str,
    index: IndexId,
    field: str | None = None,
) -> dict:
    """Synchronize the register with the objects in the S3 bucket"""
    sync_time = datetime.now(UTC)

    prefix = f"{index}/"
    if field:
        prefix += f"{field}/"

    batch: list[tuple] = []

    async def flush():
        async with connection() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(
                    """INSERT INTO object_storage (project_id, field, filepath, path, size, last_synced)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (project_id, field, filepath) DO UPDATE
                       SET size = EXCLUDED.size, last_synced = EXCLUDED.last_synced""",
                    batch,
                )
        batch.clear()

    async for obj in scan_s3_objects(bucket, prefix):
        obj_index, obj_field, filepath = obj["key"].split("/", 2)
        path, _, _ = split_filepath(filepath)
        batch.append((obj_index, obj_field, filepath, path, obj["size"], sync_time))
        if len(batch) >= 2500:
            await flush()
    if batch:
        await flush()

    return await _clean_register(index, field=field, min_sync=sync_time)


async def delete_register(index: IndexId, field: str | None = None):
    """
    Delete all register entries for the given index and optional field.
    """
    if field:
        n = await execute("DELETE FROM object_storage WHERE project_id = %s AND field = %s", [index, field])
    else:
        n = await execute("DELETE FROM object_storage WHERE project_id = %s", [index])
    return dict(updated=n, total=n)


async def delete_objects(index: IndexId, field: str, filepaths: list[str]):
    n = await execute(
        "DELETE FROM object_storage WHERE project_id = %s AND field = %s AND filepath = ANY(%s)", [index, field, filepaths]
    )
    return dict(updated=n, total=n)


async def _clean_register(
    index: IndexId, field: str | None = None, min_sync: datetime | None = None, keep_pending: bool = True
) -> dict:
    """
    Remove all entries that were not synced since min_sync (or not synced at all if min_sync is None).

    If keep_pending is True, we do not delete entries for which the presigned post is still valid
    """
    conditions: list[str] = ["project_id = %s"]
    params: list[Any] = [index]
    if min_sync:
        conditions.append("(last_synced IS NULL OR last_synced < %s)")
        params.append(min_sync)
    else:
        conditions.append("last_synced IS NULL")
    if field:
        conditions.append("field = %s")
        params.append(field)
    if keep_pending:
        pending_time = datetime.now(UTC) - timedelta(hours=PRESIGNED_POST_HOURS_VALID + 1)
        conditions.append("(registered IS NULL OR registered <= %s)")
        params.append(pending_time)
    n = await execute(f"DELETE FROM object_storage WHERE {' AND '.join(conditions)}", params)  # type: ignore[arg-type]
    return dict(updated=n, total=n)


async def _get_current(index: IndexId, field: str, objects: list[RegisterObject]) -> dict[str, int]:
    """
    Get the sizes of the objects that are already registered, as a {filepath: size} dictionary
    """
    rows = await fetch_all(
        "SELECT filepath, size FROM object_storage WHERE project_id = %s AND field = %s AND filepath = ANY(%s)",
        [index, field, [obj.filepath for obj in objects]],
    )
    return {row["filepath"]: row["size"] for row in rows}


async def _get_total_size(index: IndexId) -> int:
    row = await fetch_one("SELECT coalesce(sum(size), 0) AS total FROM object_storage WHERE project_id = %s", [index])
    return int(row["total"]) if row else 0


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


async def _raise_if_invalid_type(index: IndexId, field: str, objects: dict[str, ObjectStorage]) -> None:
    allowed_types = ["image", "video", "audio"]
    f = (await list_fields(index)).get(field)
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
