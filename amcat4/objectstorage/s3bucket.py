"""
Interact with S3-compatible object storage (e.g., AWS S3, MinIO, SeaweedFS, Cloudflare R2).
"""

from datetime import datetime
from typing import Any, AsyncIterable, Literal, Optional
from typing_extensions import TypedDict

import async_lru
from botocore.exceptions import ClientError
from types_aiobotocore_s3.type_defs import (
    GetObjectOutputTypeDef,
    HeadObjectOutputTypeDef,
    ListObjectsV2RequestTypeDef,
    ObjectIdentifierTypeDef,
)

from amcat4.config import get_settings
from amcat4.connections import s3

PRESIGNED_POST_HOURS_VALID = 6


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


async def get_bucket(bucket: Literal["multimedia", "backup"]) -> str:
    """
    Get one of the standard buckets, taking into account whether we are using a test database.
    """
    use_test_db = get_settings().use_test_db
    if use_test_db:
        testbucket = f"test-{bucket}"
        return await _create_or_get_bucket_name(testbucket)
    else:
        return await _create_or_get_bucket_name(bucket)


@async_lru.alru_cache(maxsize=1000)
async def _create_or_get_bucket_name(bucket: str) -> str:
    try:
        await s3().head_bucket(Bucket=bucket)
    except ClientError as e:
        error = e.response.get("Error", {})
        if error.get("Code") in ("404", "NoSuchBucket"):
            await s3().create_bucket(Bucket=bucket)
        else:
            raise
    return bucket


async def list_s3_objects(
    bucket: str,
    prefix: Optional[str] = None,
    page_size: int = 1000,
    next_page_token: Optional[str] = None,
    recursive=True,
    presigned: bool = False,
) -> ListResults:
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

    res = await s3().list_objects_v2(**params)

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
                        "presigned_get": presigned and await presigned_get(bucket, content["Key"]) or None,
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


async def scan_s3_objects(bucket: str, prefix: str = "", page_size=5000) -> AsyncIterable[ListObject]:
    paginator = s3().get_paginator("list_objects_v2")

    async for page in paginator.paginate(Bucket=bucket, Prefix=prefix, PaginationConfig={"PageSize": page_size}):
        if "Contents" in page:
            for content in page["Contents"]:
                if "Key" in content:
                    yield ListObject(
                        is_dir=False,
                        key=content["Key"],
                        size=content.get("Size"),
                        last_modified=content.get("LastModified"),
                        presigned_get=None,
                        etag=content.get("ETag", "").strip('"') if content.get("ETag") else None,
                    )


async def stat_s3_object(bucket: str, key: str) -> HeadObjectOutputTypeDef:
    try:
        return await s3().head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        error = e.response.get("Error", {})
        if error.get("Code") == "404":
            raise FileNotFoundError(f"Object {key} not found in bucket")
        else:
            raise


async def get_s3_object(bucket: str, key: str, first_bytes: int | None = None) -> GetObjectOutputTypeDef:
    if first_bytes is not None:
        res = await s3().get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{first_bytes - 1}")
    else:
        res = await s3().get_object(Bucket=bucket, Key=key)

    return res


async def delete_s3_by_prefix(bucket: str, prefix: str):
    paginator = s3().get_paginator("list_objects_v2")
    async for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        if "Contents" in page:
            keys = [obj["Key"] for obj in page["Contents"] if "Key" in obj]
            await delete_s3_by_key(bucket, keys)


async def delete_s3_by_key(bucket: str, keys: list[str]):
    to_delete: list[ObjectIdentifierTypeDef] = [{"Key": key} for key in keys]
    if to_delete:
        await s3().delete_objects(Bucket=bucket, Delete={"Objects": to_delete})


async def add_s3_object(bucket: str, key: str, data: bytes):
    await s3().put_object(Bucket=bucket, Key=key, Body=data)


async def presigned_post(
    bucket: str, key: str, content_type: str = "", size: int | None = None, redirect: str = ""
) -> tuple[str, dict[str, str]]:
    conditions: list[Any] = [{"bucket": bucket}]
    fields: dict[str, str] = {}

    if content_type:
        conditions.append(["starts-with", "$Content-Type", content_type])
        fields["Content-Type"] = content_type
    if size is not None:
        conditions.append(["content-length-range", 0, size])
    if redirect:
        conditions.append({"success_action_redirect": redirect})
        fields["success_action_redirect"] = redirect

    pp = await s3().generate_presigned_post(
        Bucket=bucket,
        Key=key,
        Fields=fields,
        Conditions=conditions,
        ExpiresIn=PRESIGNED_POST_HOURS_VALID * 3600,
    )
    return pp["url"], pp["fields"]


async def presigned_get(bucket: str, key: str, hours_valid=24, **kwargs) -> str:
    params = {"Bucket": bucket, "Key": key, **kwargs}
    params = {k: v for k, v in params.items() if v is not None}

    return await s3().generate_presigned_url("get_object", Params=params, ExpiresIn=hours_valid * 3600)


async def get_object_head(bucket: str, key: str) -> HeadObjectOutputTypeDef:
    res = await s3().head_object(Bucket=bucket, Key=key)
    return res
