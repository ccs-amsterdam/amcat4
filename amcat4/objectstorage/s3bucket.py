"""
Interact with S3-compatible object storage (e.g., AWS S3, MinIO, SeaweedFS, Cloudflare R2).
"""

from datetime import datetime
import functools
from typing import Any, Literal, Optional, TypedDict

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


class ListObject(TypedDict):
    is_dir: bool
    key: str
    size: int | None
    last_modified: datetime | None
    presigned_get: str | None
    etag: str | None


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


def get_bucket(bucket: Literal["multimedia", "backup"]) -> str:
    """
    Get one of the standard buckets, taking into account whether we are using a test database.
    """
    use_test_db = get_settings().use_test_db
    if use_test_db:
        testbucket = f"test-{bucket}"
        return _create_or_get_bucket_name(testbucket)
    else:
        return _create_or_get_bucket_name(bucket)


@functools.lru_cache()
def _create_or_get_bucket_name(bucket: str) -> str:
    s3 = get_s3_client()

    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as e:
        error = e.response.get("Error", {})
        if error.get("Code") in ("404", "NoSuchBucket"):
            s3.create_bucket(Bucket=bucket)
        else:
            raise
    return bucket


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
                        "etag": content.get("ETag", "").strip('"') if content.get("ETag") else None,
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
                    "etag": None,
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


def delete_from_bucket(bucket: str, prefix: str):
    s3 = get_s3_client()

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        if "Contents" in page:
            to_delete: list[ObjectIdentifierTypeDef] = [
                {"Key": obj.get("Key", "[never]")} for obj in page["Contents"] if obj.get("Key") is not None
            ]
            if to_delete:
                s3.delete_objects(Bucket=bucket, Delete={"Objects": to_delete})


def add_s3_object(bucket: str, key: str, data: bytes):
    s3 = get_s3_client()
    s3.put_object(Bucket=bucket, Key=key, Body=data)


def presigned_post(
    bucket: str, key: str, type_prefix: str = "", redirect: str = "", days_valid: int = 1
) -> tuple[str, dict[str, str]]:
    s3 = get_s3_client()

    conditions: list[Any] = [{"bucket": bucket}]
    fields: dict[str, str] = {}

    if type_prefix:
        conditions.append(["starts-with", "$Content-Type", type_prefix])
    if redirect:
        conditions.append({"success_action_redirect": redirect})
        fields["success_action_redirect"] = redirect

    pp = s3.generate_presigned_post(
        Bucket=bucket,
        Key=key,
        Fields=fields,
        Conditions=conditions,
        ExpiresIn=days_valid * 24 * 3600,
    )
    return pp["url"], pp["fields"]


def presigned_get(bucket: str, key: str, hours_valid=24, **kwargs) -> str:
    s3 = get_s3_client()
    params = {"Bucket": bucket, "Key": key, **kwargs}

    return s3.generate_presigned_url("get_object", Params=params, ExpiresIn=hours_valid * 3600)


def get_object_head(bucket: str, key: str, ignore_missing=False) -> HeadObjectOutputTypeDef | None:
    s3 = get_s3_client()
    try:
        res = s3.head_object(Bucket=bucket, Key=key)
        return res
    except Exception as e:
        if ignore_missing and "NotFound" in str(e):
            return None
        raise
