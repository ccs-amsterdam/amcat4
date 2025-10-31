"""
Multimedia features for AmCAT

AmCAT can link to a minio/S3 object store to provide access to multimedia content attached to documents.
The object store needs to be configured in the server settings.
"""

from io import BytesIO
from typing import Iterable, Optional, List, Dict, Any

from mypy_boto3_s3.type_defs import CommonPrefixTypeDef, HeadObjectOutputTypeDef, ObjectIdentifierTypeDef, ObjectTypeDef
from amcat4.config import get_settings, v

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from mypy_boto3_s3.client import S3Client
import functools


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
        raise Exception(f"Cannot connect to S3 {get_settings().minio_host!r}: {e}")


def _connect_s3() -> Optional[S3Client]:
    settings = get_settings()
    if settings.minio_host is None:
        return None
    if settings.minio_secret_key is None or settings.minio_access_key is None:
        raise ValueError("minio_access_key or minio_secret_key not specified")

    endpoint_url = f"http{'s' if settings.minio_tls else ''}://{settings.minio_host}"

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=Config(signature_version="s3v4"),
    )


def bucket_name(index: str) -> str:
    return index.replace("_", "-")


def get_bucket(s3: S3Client, index: str, create_if_needed=True) -> str:
    """
    Get the bucket name for this index. If create_if_needed is True, create the bucket if it doesn't exist.
    Returns the bucket name, or "" if it doesn't exist and create_if_needed is False.
    """
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


def list_multimedia_objects(
    index: str, prefix: Optional[str] = None, start_after: Optional[str] = None, recursive=True
) -> Iterable[ObjectTypeDef | CommonPrefixTypeDef]:
    s3 = get_s3_client()
    bucket = get_bucket(s3, index, create_if_needed=False)
    if not bucket:
        return

    paginator = s3.get_paginator("list_objects_v2")
    kwargs = {"Bucket": bucket}
    if prefix:
        kwargs["Prefix"] = prefix
    if start_after:
        kwargs["StartAfter"] = start_after
    if not recursive:
        kwargs["Delimiter"] = "/"

    for page in paginator.paginate(**kwargs):
        for content in page.get("Contents", []):
            yield content
        if not recursive:
            for common_prefix in page.get("CommonPrefixes", []):
                yield common_prefix


def stat_multimedia_object(index: str, key: str) -> HeadObjectOutputTypeDef:
    s3 = get_s3_client()
    bucket = get_bucket(s3, index, create_if_needed=False)
    if not bucket:
        raise ValueError(f"Bucket for {index} does not exist")
    try:
        return s3.head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        error = e.response.get("Error", {})
        if error.get("Code") == "404":
            raise FileNotFoundError(f"Object {key} not found in bucket for index {index}")
        else:
            raise


def get_multimedia_object(index: str, key: str) -> bytes:
    s3 = get_s3_client()
    bucket = get_bucket(s3, index, create_if_needed=False)
    if not bucket:
        raise ValueError(f"Bucket for {index} does not exist")
    res = s3.get_object(Bucket=bucket, Key=key)
    return res["Body"].read()


def delete_bucket(s3: S3Client, index: str):
    bucket = get_bucket(s3, index, create_if_needed=False)
    if not bucket:
        return

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        ## TODO: type seems of. Check if Key should actually be Name
        if "Contents" in page:
            to_delete: list[ObjectIdentifierTypeDef] = [
                {"Key": obj.get("Key", "[never]")} for obj in page["Contents"] if obj.get("Key") is not None
            ]
            if to_delete:
                s3.delete_objects(Bucket=bucket, Delete={"Objects": to_delete})

    s3.delete_bucket(Bucket=bucket)


def add_multimedia_object(index: str, key: str, data: bytes):
    s3 = get_s3_client()
    bucket = get_bucket(s3, index)
    s3.put_object(Bucket=bucket, Key=key, Body=data)


def presigned_post(index: str, key_prefix: str = "", days_valid=1):
    s3 = get_s3_client()
    bucket = get_bucket(s3, index)

    conditions = []
    if key_prefix:
        conditions.append(["starts-with", "$key", key_prefix])

    return s3.generate_presigned_post(
        Bucket=bucket, Key="${filename}", Fields=None, Conditions=conditions, ExpiresIn=days_valid * 24 * 3600
    )


def presigned_get(index: str, key: str, days_valid=1) -> str:
    s3 = get_s3_client()
    bucket = get_bucket(s3, index, create_if_needed=False)
    if not bucket:
        raise ValueError(f"Bucket for {index} does not exist")

    return s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=days_valid * 24 * 3600)
