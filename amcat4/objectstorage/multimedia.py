from typing import Tuple

from mypy_boto3_s3.type_defs import HeadObjectOutputTypeDef

from amcat4.elastic import es
from amcat4.models import ObjectStorage
from amcat4.objectstorage import s3bucket
from amcat4.objectstorage.s3bucket import (
    ListResults,
    delete_from_bucket,
    get_bucket,
    get_object_head,
    list_s3_objects,
    presigned_get,
    presigned_post,
)
from amcat4.systemdata.objectstorage import delete_s3_register, refresh_objectstorage
from amcat4.systemdata.versions import system_index


def multimedia_key(ix: str, field: str, filepath: str) -> str:
    return f"{ix}/{field}/{filepath}"


def multimedia_bucket() -> str:
    return get_bucket("multimedia")


def get_multimedia_meta(ix: str, field: str, filepath: str) -> HeadObjectOutputTypeDef | None:
    bucket = multimedia_bucket()
    key = multimedia_key(ix, field, filepath)
    return get_object_head(bucket, key)


def delete_project_multimedia(ix: str, field: str | None = None):
    bucket = multimedia_bucket()
    prefix = f"{ix}/"

    delete_from_bucket(bucket, prefix=prefix)
    delete_s3_register(ix, field)


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
    url, form = presigned_post(bucket, key=key, type_prefix=object.content_type, size=object.size)
    return url, form


def update_multimedia_field(ix: str, doc: str, field: str, hash: str, size: int):
    es().update(index=ix, id=doc, doc={field: {"hash": hash, "size": size}}, refresh=True)
