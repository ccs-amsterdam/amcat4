from contextlib import AsyncExitStack
from typing import Any, Callable

from aiobotocore.config import AioConfig
from aiobotocore.session import get_session
from types_aiobotocore_s3.client import S3Client

from amcat4.config import get_settings


class S3SessionHolder:
    context_stack: AsyncExitStack | None = None
    client: S3Client | None = None


S3_SESSION = S3SessionHolder()


def get_s3_client() -> S3Client:
    if S3_SESSION.client is None:
        raise ConnectionError("S3 client not started")
    return S3_SESSION.client


async def start_s3_client() -> S3Client | None:
    if s3_enabled() is False:
        return None  # type: ignore

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

    # client is an async context manager, so we use an AsyncExitStack to manage its lifetime
    S3_SESSION.context_stack = AsyncExitStack()
    S3_SESSION.client = await S3_SESSION.context_stack.enter_async_context(client)

    return S3_SESSION.client


async def close_s3_session():
    if S3_SESSION.context_stack is not None:
        await S3_SESSION.context_stack.aclose()
        S3_SESSION.context_stack = None
        S3_SESSION.client = None


def s3_enabled() -> bool:
    settings = get_settings()
    return all([settings.s3_host, settings.s3_access_key, settings.s3_secret_key])
