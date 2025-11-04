from typing import Literal
from amcat4.objectstorage.s3bucket import get_etag, bucket_name, get_index_bucket, presigned_post, presigned_get
from amcat4.systemdata.fields import list_fields


CONTENT_TYPE = Literal["image", "video", "audio"]
ALLOWED_CONTENT_PREFIXES: dict[CONTENT_TYPE, str] = {
    "image": "image/",
    "video": "video/",
    "audio": "audio/",
    # "pdf": "application/pdf", # to be added later
}


def multimedia_key(ix: str, field: str, path: str) -> str:
    return f"multimedia/{field}/{path}"


def get_multimedia_etag(ix: str, field: str, path: str) -> str:
    bucket = bucket_name(ix)
    key = multimedia_key(ix, field, path)
    return get_etag(bucket, key)


def presigned_multimedia_get(ix: str, field: str, path: str, immutable_cache: bool) -> str:
    bucket = bucket_name(ix)
    key = multimedia_key(ix, field, path)

    if immutable_cache:
        cache = "public, max-age=31536000, immutable"
    else:
        cache = "no-cache, must-revalidate"

    return presigned_get(bucket, key, ResponseCacheControl=cache)


def presigned_multimedia_post(ix: str, field: str) -> dict:
    bucket = get_index_bucket(ix)

    docfield = list_fields(ix).get(field)
    if not docfield:
        raise ValueError(f"Field {field} does not exist in index {ix}")

    type = docfield.type
    if type not in ALLOWED_CONTENT_PREFIXES:
        raise ValueError(f"Field {field} is of type {type}, which is not a valid multimedia type")

    key_prefix = f"multimedia/{field}/"
    type_prefix = ALLOWED_CONTENT_PREFIXES[type]
    url, form_data = presigned_post(bucket, key_prefix=key_prefix, type_prefix=type_prefix)
    return dict(url=url, form_data=form_data, key_prefix=key_prefix, type_prefix=type_prefix)
