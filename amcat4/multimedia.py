"""
Multimedia features for AmCAT

AmCAT can link to a minio/S3 object store to provide access to multimedia content attached to documents.
The object store needs to be configured in the server settings.
"""

import datetime
from io import BytesIO
from multiprocessing import Value
import re
from typing import Iterable, Optional
from venv import create
from amcat4.config import get_settings
from minio import Minio, S3Error
from minio.deleteobjects import DeleteObject
from minio.datatypes import PostPolicy, Object
import functools


def get_minio() -> Minio:
    result = connect_minio()
    if result is None:
        raise ValueError("Could not connect to minio")
    return result


@functools.lru_cache()
def connect_minio() -> Optional[Minio]:
    try:
        return _connect_minio()
    except Exception as e:
        raise Exception(f"Cannot connect to minio {get_settings().minio_host!r}: {e}")


def _connect_minio() -> Optional[Minio]:
    settings = get_settings()
    if settings.minio_host is None:
        return None
    if settings.minio_secret_key is None or settings.minio_access_key is None:
        raise ValueError("minio_access_key or minio_secret_key not specified")
    return Minio(
        settings.minio_host,
        secure=settings.minio_tls,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
    )


def bucket_name(index: str) -> str:
    return index.replace("_", "-")


def get_bucket(minio: Minio, index: str, create_if_needed=True):
    """
    Get the bucket name for this index. If create_if_needed is True, create the bucket if it doesn't exist.
    Returns the bucket name, or "" if it doesn't exist and create_if_needed is False.
    """
    bucket = bucket_name(index)
    if not minio.bucket_exists(bucket):
        if not create_if_needed:
            return ""
        minio.make_bucket(bucket)
    return bucket


def list_multimedia_objects(
    index: str, prefix: Optional[str] = None, start_after: Optional[str] = None, recursive=True
) -> Iterable[Object]:
    minio = get_minio()
    bucket = get_bucket(minio, index, create_if_needed=False)
    if not bucket:
        return
    yield from minio.list_objects(bucket_name(index), prefix=prefix, start_after=start_after, recursive=recursive)


def stat_multimedia_object(index: str, key: str) -> Object:
    minio = get_minio()
    bucket = get_bucket(minio, index, create_if_needed=False)
    if not bucket:
        raise ValueError(f"Bucket for {index} does not exist")
    return minio.stat_object(bucket, key)


def get_multimedia_object(index: str, key: str) -> bytes:
    minio = get_minio()
    bucket = get_bucket(minio, index, create_if_needed=False)
    if not bucket:
        raise ValueError(f"Bucket for {index} does not exist")
    res = minio.get_object(bucket, key)
    return res.read()


def delete_bucket(minio: Minio, index: str):
    bucket = get_bucket(minio, index, create_if_needed=False)
    if not bucket:
        return
    to_delete = [DeleteObject(x.object_name) for x in minio.list_objects(bucket, recursive=True) if x.object_name]
    errors = list(minio.remove_objects(bucket, to_delete))
    if errors:
        raise Exception(f"Error on deleting objects: {errors}")
    minio.remove_bucket(bucket)


def add_multimedia_object(index: str, key: str, bytes: bytes):
    minio = get_minio()
    bucket = get_bucket(minio, index)
    data = BytesIO(bytes)
    minio.put_object(bucket, key, data, len(bytes))


def presigned_post(index: str, key_prefix: str = "", days_valid=1):
    minio = get_minio()
    bucket = get_bucket(minio, index)
    policy = PostPolicy(bucket, expiration=datetime.datetime.now() + datetime.timedelta(days=days_valid))
    policy.add_starts_with_condition("key", key_prefix)
    minio_host = (
        get_settings().public_minio_host or f"http{'s' if get_settings().minio_tls else ''}://{get_settings().minio_host}"
    )
    url = f"{minio_host}/{bucket}"
    return url, minio.presigned_post_policy(policy)


def presigned_get(index: str, key, days_valid=1):
    minio = get_minio()
    bucket = get_bucket(minio, index)
    url = minio.presigned_get_object(bucket, key, expires=datetime.timedelta(days=days_valid))
    public_host = get_settings().public_minio_host
    if public_host:
        url = re.sub("https?://.*?/", "", url)
        url = f"{public_host}/{url}"
    return url
