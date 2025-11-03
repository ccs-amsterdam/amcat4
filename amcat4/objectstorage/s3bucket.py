"""
Interact with S3-compatible object storage (e.g., AWS S3, MinIO, SeaweedFS, Cloudflare R2).
"""

from datetime import datetime
import functools
import os
from typing import Any, Iterable, Optional, TypedDict

from mypy_boto3_s3.type_defs import (
    HeadObjectOutputTypeDef,
    ListObjectsV2RequestTypeDef,
    ObjectIdentifierTypeDef,
)
from amcat4.config import get_settings

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from mypy_boto3_s3.client import S3Client

## TODO: think about best way to sync elastic and s3 storage.
## For security it would also be better if access to s3 objects
## is not based on relation index name and bucket name.


## TODO: now not used, because not possible with presigned posts.
ALLOWED_CONTENT_TYPES = [
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
    "audio/mp4",
    "application/pdf",
]


class ListObject(TypedDict):
    is_dir: bool
    key: str
    size: int | None
    last_modified: datetime | None
    presigned_get: str | None


class ListResults(TypedDict):
    items: list[ListObject]
    next_page_token: str | None
    is_last_page: bool


def s3_enabled() -> bool:
    settings = get_settings()
    return all([settings.s3_host, settings.s3_access_key, settings.s3_secret_key])


def get_s3_client() -> S3Client:
    result = connect_s3()
    if result is None:
        raise ValueError("Could not connect to S3")
    return result


@functools.lru_cache()
def connect_s3() -> Optional[S3Client]:
    try:
        return _connect_s3()
    except Exception as e:
        raise Exception(f"Cannot connect to S3 {get_settings().s3_host!r}: {e}")


def _connect_s3() -> Optional[S3Client]:
    settings = get_settings()

    if settings.s3_host is None:
        return None
    if settings.s3_access_key is None or settings.s3_secret_key is None:
        raise ValueError("s3_access_key or s3_secret_key not specified")

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_host,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
    )


def bucket_name(index: str) -> str:
    indexname = index.replace("_", "-")
    use_test_db = get_settings().use_test_db
    if use_test_db:
        return f"test-index-{indexname}"
    else:
        return f"index-{indexname}"


def get_index_bucket(index: str, create_if_needed=True) -> str:
    """
    Get the bucket name for this index. If create_if_needed is True, create the bucket if it doesn't exist.
    Returns the bucket name, or "" if it doesn't exist and create_if_needed is False.
    """
    s3 = get_s3_client()

    bucket = bucket_name(index)

    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as e:
        error = e.response.get("Error", {})
        if error.get("Code") in ("404", "NoSuchBucket"):
            if not create_if_needed:
                return ""
            s3.create_bucket(Bucket=bucket)
        else:
            raise
    return bucket


def delete_index_bucket(index: str, ignore_missing=True):
    bucket = bucket_name(index)
    delete_bucket(bucket, ignore_missing=ignore_missing)


def list_s3_objects(
    bucket: str,
    prefix: Optional[str] = None,
    page_size: int = 1000,
    next_page_token: Optional[str] = None,
    recursive=True,
    presigned: bool = False,
) -> ListResults:
    s3 = get_s3_client()

    params: ListObjectsV2RequestTypeDef = {
        "Bucket": bucket,
        "MaxKeys": page_size,
    }
    if prefix:
        params["Prefix"] = prefix
    if next_page_token:
        params["ContinuationToken"] = next_page_token
    if not recursive:
        params["Delimiter"] = "/"

    res = s3.list_objects_v2(**params)

    objects: list[ListObject] = []

    if "Contents" in res:
        for content in res["Contents"]:
            if "Key" in content:
                objects.append(
                    {
                        "is_dir": False,
                        "key": content["Key"],
                        "size": content.get("Size"),
                        "last_modified": content.get("LastModified"),
                        "presigned_get": presigned and presigned_get(bucket, content["Key"]) or None,
                    }
                )

    if not recursive and "CommonPrefixes" in res:
        for common_prefix in res["CommonPrefixes"]:
            objects.append(
                {
                    "is_dir": True,
                    "key": common_prefix.get("Prefix", ""),
                    "size": None,
                    "last_modified": None,
                    "presigned_get": None,
                }
            )

    return {
        "items": objects,
        "next_page_token": res.get("NextContinuationToken"),
        "is_last_page": not res.get("IsTruncated", False),
    }


def stat_s3_object(bucket: str, key: str) -> HeadObjectOutputTypeDef:
    s3 = get_s3_client()

    try:
        return s3.head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        error = e.response.get("Error", {})
        if error.get("Code") == "404":
            raise FileNotFoundError(f"Object {key} not found in bucket")
        else:
            raise


def get_s3_object(bucket: str, key: str) -> bytes:
    s3 = get_s3_client()
    res = s3.get_object(Bucket=bucket, Key=key)
    return res["Body"].read()


def delete_bucket(bucket: str, ignore_missing=True):
    s3 = get_s3_client()

    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            if "Contents" in page:
                to_delete: list[ObjectIdentifierTypeDef] = [
                    {"Key": obj.get("Key", "[never]")} for obj in page["Contents"] if obj.get("Key") is not None
                ]
                if to_delete:
                    s3.delete_objects(Bucket=bucket, Delete={"Objects": to_delete})

        s3.delete_bucket(Bucket=bucket)
    except Exception as e:
        if ignore_missing and "NoSuchBucket" in str(e):
            return
        raise


def add_s3_object(bucket: str, key: str, data: bytes):
    s3 = get_s3_client()
    s3.put_object(Bucket=bucket, Key=key, Body=data)


def presigned_post(bucket: str, key_prefix: str = "", days_valid: int = 1) -> tuple[str, dict[str, str]]:
    s3 = get_s3_client()

    conditions: list[Any] = [{"bucket": bucket}]

    if key_prefix:
        conditions.append(["starts-with", "$key", key_prefix])

    # It seems this is impossible. Can only have one content-type condition, not multiple.
    # for content_type in ALLOWED_CONTENT_TYPES:
    #     conditions.append(["eq", "$Content-Type", content_type])

    pp = s3.generate_presigned_post(
        Bucket=bucket, Key="${filename}", Fields=None, Conditions=conditions, ExpiresIn=days_valid * 24 * 3600
    )
    return pp["url"], pp["fields"]


def presigned_get(bucket: str, key: str, hours_valid=24, **kwargs) -> str:
    s3 = get_s3_client()
    params = {"Bucket": bucket, "Key": key, **kwargs}

    return s3.generate_presigned_url("get_object", Params=params, ExpiresIn=hours_valid * 3600)


def get_etag(bucket: str, key: str) -> str:
    s3 = get_s3_client()
    res = s3.head_object(Bucket=bucket, Key=key)
    return res["ETag"].strip('"')
