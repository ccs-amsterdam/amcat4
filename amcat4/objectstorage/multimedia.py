from typing import Tuple, TypedDict

import magic

from amcat4.elastic import es
from amcat4.models import ObjectStorage
from amcat4.objectstorage.s3bucket import (
    delete_from_bucket,
    get_bucket,
    get_object_head,
    get_s3_object,
    presigned_get,
    presigned_post,
)
from amcat4.systemdata.objectstorage import (
    ALLOWED_MIME_TYPES,
    delete_register,
    get_content_type,
    refresh_objectstorage,
    split_filepath,
)


def multimedia_key(ix: str, field: str, filepath: str) -> str:
    return f"{ix}/{field}/{filepath}"


def multimedia_bucket() -> str:
    return get_bucket("multimedia")


class MultimediaMeta(TypedDict):
    size: int
    etag: str
    ext_content_type: str | None
    real_content_type: str | None


def get_multimedia_meta(ix: str, field: str, filepath: str, read_mimetype: bool = True) -> MultimediaMeta | None:
    """
    Get metadata about a multimedia object stored in S3.
    If read_mimetype is True, read the first bytes of the object to determine the real content type.
    This is slower but safer
    """
    bucket = multimedia_bucket()
    key = multimedia_key(ix, field, filepath)
    _, _, ext = split_filepath(filepath)
    ext_content_type = ALLOWED_MIME_TYPES.get(ext, None)

    try:
        if read_mimetype:
            obj = get_s3_object(bucket, key, first_bytes=32)
            real_content_type = str(magic.from_buffer(obj["Body"].read(32), mime=True))
        else:
            obj = get_object_head(bucket, key)
            real_content_type = None

        return MultimediaMeta(
            size=obj["ContentLength"],
            etag=obj["ETag"].strip('"'),
            ext_content_type=ext_content_type,
            real_content_type=real_content_type,
        )

    except Exception:
        return None


def delete_project_multimedia(ix: str, field: str | None = None):
    bucket = multimedia_bucket()
    prefix = f"{ix}/"

    delete_from_bucket(bucket, prefix=prefix)
    delete_register(ix, field)


def refresh_multimedia_register(ix: str, field: str | None = None) -> dict:
    bucket = multimedia_bucket()
    return refresh_objectstorage(bucket, ix, field)


def presigned_multimedia_get(ix: str, field: str, filepath: str, immutable_cache: bool) -> str:
    bucket = multimedia_bucket()
    key = multimedia_key(ix, field, filepath)

    if immutable_cache:
        ## Immutable cache for 1 year on browser (private) side
        cache = "private, max-age=31536000, immutable"
    else:
        cache = "no-cache, must-revalidate"

    return presigned_get(bucket, key, ResponseCacheControl=cache)


def presigned_multimedia_post(ix: str, object: ObjectStorage) -> Tuple[str, dict[str, str]]:
    bucket = multimedia_bucket()
    key = multimedia_key(ix, object.field, object.filepath)
    content_type = get_content_type(object.filepath)
    size = object.size

    if content_type is None:
        raise ValueError(f"Unsupported multimedia file extension for file {object.filepath}")

    url, form = presigned_post(bucket, key=key, type_prefix=content_type, size=size)
    return url, form


def update_multimedia_field(ix: str, doc: str, field: str, hash: str, size: int):
    es().update(index=ix, id=doc, doc={field: {"hash": hash, "size": size}}, refresh=True)
