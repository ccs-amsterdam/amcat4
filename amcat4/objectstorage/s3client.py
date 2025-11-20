from typing import Any, Callable

from aiobotocore.config import AioConfig
from aiobotocore.session import get_session
from types_aiobotocore_s3.client import S3Client

from amcat4.config import get_settings


class S3SessionHolder:
    close: Callable[..., Any] | None = None
    client: S3Client | None = None


S3_SESSION = S3SessionHolder()


def get_s3_client() -> S3Client:
    if S3_SESSION.client is None:
        raise ConnectionError("S3 client not started")
    return S3_SESSION.client


async def start_s3_client() -> S3Client:
    settings = get_settings()

    if settings.s3_host is None:
        raise ValueError("s3_host not specified")
    if settings.s3_access_key is None or settings.s3_secret_key is None:
        raise ValueError("s3_access_key or s3_secret_key not specified")

    ## It seems aioboto3 uses some of the sync boto3 types, so we need to hack around typing here.
    session = get_session()
    client = session.create_client(
        service_name="s3",
        endpoint_url=settings.s3_host,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=AioConfig(signature_version="s3v4"),
    )

    ## It seems we only get a context manager, so we take
    ## it apart here to handle the lifecycle ourselves.
    S3_SESSION.client = await client.__aenter__()
    S3_SESSION.close = client.__aexit__

    return S3_SESSION.client


async def close_s3_session():
    if S3_SESSION.close is not None:
        await S3_SESSION.close()


def s3_enabled() -> bool:
    settings = get_settings()
    return all([settings.s3_host, settings.s3_access_key, settings.s3_secret_key])
