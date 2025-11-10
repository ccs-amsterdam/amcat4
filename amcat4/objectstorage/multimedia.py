from typing import Literal

from mypy_boto3_s3.type_defs import HeadObjectOutputTypeDef

from amcat4.elastic import es
from amcat4.elastic.util import BulkInsertAction, es_bulk_upsert, index_scan
from amcat4.models import DocumentField
from amcat4.objectstorage.s3bucket import (
    delete_from_bucket,
    get_bucket,
    get_object_head,
    presigned_get,
    presigned_post,
)
from amcat4.systemdata.fields import list_fields

CONTENT_TYPE = Literal["image", "video", "audio"]
ALLOWED_CONTENT_PREFIXES: dict[CONTENT_TYPE, str] = {
    "image": "image/",
    "video": "video/",
    "audio": "audio/",
    # "pdf": "application/pdf", # to be added later
}


def get_multimedia_meta(ix: str, doc: str, field: str) -> HeadObjectOutputTypeDef | None:
    bucket = get_bucket("multimedia")
    key = multimedia_key(ix, doc, field)
    return get_object_head(bucket, key)


def delete_project_multimedia(ix: str):
    bucket = get_bucket("multimedia")
    prefix = f"{ix}/"
    delete_from_bucket(bucket, prefix=prefix)


def multimedia_key(ix: str, doc: str, field: str) -> str:
    return f"{ix}/{doc}/{field}"


def presigned_multimedia_get(ix: str, doc: str, field: str, immutable_cache: bool) -> str:
    bucket = get_bucket("multimedia")
    key = multimedia_key(ix, doc, field)

    ## Note that this does not mean that ix/doc/field is immutably cached.
    ## it applies to the gatekeeper endpoint, which should only set immutable_cache
    ## to TRUE if the url includes the Etag (cache buster).
    if immutable_cache:
        cache = "private, max-age=31536000, immutable"
    else:
        cache = "no-cache, must-revalidate"

    return presigned_get(bucket, key, ResponseCacheControl=cache)


def presigned_multimedia_post(ix: str, doc: str, field: str, size: int, redirect: str = "") -> dict:
    bucket = get_bucket("multimedia")

    docfield = list_fields(ix, auto_repair=False).get(field)
    if not docfield:
        raise ValueError(f"Field {field} does not exist in index {ix}")

    type = docfield.type
    if type not in ALLOWED_CONTENT_PREFIXES:
        raise ValueError(f"Field {field} is of type {type}, which is not a valid multimedia type")

    key = multimedia_key(ix, doc, field)
    type_prefix = ALLOWED_CONTENT_PREFIXES[type]

    url, form_data = presigned_post(bucket, key=key, type_prefix=type_prefix, size=size, redirect=redirect)
    return dict(url=url, form_data=form_data, type_prefix=type_prefix)


def update_multimedia_field(ix: str, doc: str, field: str, hash: str, size: int):
    es().update(index=ix, id=doc, doc={field: {"hash": hash, "size": size}}, refresh=True)
