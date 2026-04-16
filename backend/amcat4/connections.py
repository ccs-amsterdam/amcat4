import logging
from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncGenerator

import httpx
from aiobotocore.config import AioConfig
from aiobotocore.session import get_session
from elasticsearch import AsyncElasticsearch
from types_aiobotocore_s3.client import S3Client

from amcat4.config import get_settings


class AmcatConnections:
    elastic: AsyncElasticsearch | None
    s3_client: S3Client | None
    s3_context_stack: AsyncExitStack | None
    http_client: httpx.AsyncClient | None

    def __init__(
        self,
        elastic: AsyncElasticsearch | None = None,
        s3_client: S3Client | None = None,
        s3_proxy_client: S3Client | None = None,
        s3_context_stack: AsyncExitStack | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.elastic = elastic
        self.s3_client = s3_client
        self.s3_proxy_client = s3_client
        self.s3_context_stack = s3_context_stack
        self.http_client = http_client


CONNECTIONS = AmcatConnections(s3_client=None, s3_proxy_client=None, elastic=None, http_client=None)  # type: ignore


@asynccontextmanager
async def amcat_connections() -> AsyncGenerator[None, None]:
    """
    The main context manager to start and stop connections used by amcat.
    Always use this once (and only once):
        - For running the server: in the FastAPI startup and shutdown events
        - For tests: in the setup fixture in the tests
        - For CLI commands: within the CLI command
    """
    try:
        await _start_s3()
        await _start_elastic()
        await _start_http()
        yield
    finally:
        await _close_s3()
        await _close_elastic()
        await _close_http()


def es() -> AsyncElasticsearch:
    """
    Access the elasticsearch connection.
    """
    if CONNECTIONS.elastic is None:
        raise ConnectionError("Elasticsearch connection not initialized")
    return CONNECTIONS.elastic


def s3() -> S3Client:
    """
    Access the s3 client.
    """
    if CONNECTIONS.s3_client is None:
        raise ConnectionError("S3 client not started")
    return CONNECTIONS.s3_client


def s3_public() -> S3Client:
    """
    Only use this for creating presigned requests for the public
    s3 server. If the s3 server is not publicly accessible, set s3_use_proxy
    to use the s3_proxy_client, which signs urls
    """
    settings = get_settings()
    use_proxy = settings.s3_use_proxy and not settings.test_mode
    s3 = CONNECTIONS.s3_proxy_client if use_proxy else CONNECTIONS.s3_client
    if s3 is None:
        raise ConnectionError("S3 client not started")
    return s3


def s3_enabled() -> bool:
    settings = get_settings()
    return all([settings.s3_host, settings.s3_access_key, settings.s3_secret_key])


def http() -> httpx.AsyncClient:
    if CONNECTIONS.http_client is None:
        raise ConnectionError("HTTP client not started")
    return CONNECTIONS.http_client


async def _start_elastic():
    """
    Check whether we can connect with elastic
    """
    settings = get_settings()
    logging.debug(
        f"Connecting with elasticsearch at {settings.elastic_host}, password? {'yes' if settings.elastic_password else 'no'} "
    )

    if settings.elastic_password:
        host = settings.elastic_host
        if settings.elastic_verify_ssl is None:
            verify_certs = "localhost" in (host or "")
        else:
            verify_certs = settings.elastic_verify_ssl

        CONNECTIONS.elastic = AsyncElasticsearch(
            host,
            basic_auth=("elastic", settings.elastic_password),
            verify_certs=verify_certs,
        )
    else:
        CONNECTIONS.elastic = AsyncElasticsearch(settings.elastic_host or None)

    if not await CONNECTIONS.elastic.ping():
        raise ConnectionError(f"Cannot connect to elasticsearch server {settings.elastic_host}")


async def _close_elastic() -> None:
    if CONNECTIONS.elastic is not None:
        await CONNECTIONS.elastic.close()
        CONNECTIONS.elastic = None


async def _start_s3() -> None:
    if s3_enabled() is False:
        return None

    settings = get_settings()

    if settings.s3_host is None:
        raise ValueError("s3_host not specified")
    if settings.s3_access_key is None or settings.s3_secret_key is None:
        raise ValueError("s3_access_key or s3_secret_key not specified")

    session = get_session()
    client = session.create_client(
        service_name="s3",
        endpoint_url=settings.s3_host,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=AioConfig(signature_version="s3v4"),
    )

    # If the s3 server is hosted directly with docker compose, fastapi needs to
    # use a client with the internal s3_host, but presigned requests need to be created
    # for the /s3 proxy.
    proxy_url = settings.host + "/s3" if settings.s3_use_proxy else settings.s3_host
    proxy_client = session.create_client(
        service_name="s3",
        endpoint_url=proxy_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=AioConfig(signature_version="s3v4"),
    )

    CONNECTIONS.s3_context_stack = AsyncExitStack()
    CONNECTIONS.s3_client = await CONNECTIONS.s3_context_stack.enter_async_context(client)
    CONNECTIONS.s3_proxy_client = await CONNECTIONS.s3_context_stack.enter_async_context(proxy_client)


async def _close_s3():
    if CONNECTIONS.s3_context_stack is not None:
        await CONNECTIONS.s3_context_stack.aclose()
        CONNECTIONS.s3_client = None
        CONNECTIONS.s3_proxy_client = None
        CONNECTIONS.s3_context_stack = None


async def _start_http():
    # You can set global timeouts or headers here
    CONNECTIONS.http_client = httpx.AsyncClient(timeout=10.0)


async def _close_http():
    if CONNECTIONS.http_client is not None:
        await CONNECTIONS.http_client.aclose()
        CONNECTIONS.http_client = None
