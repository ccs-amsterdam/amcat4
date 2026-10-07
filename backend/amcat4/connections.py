import logging
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, AsyncGenerator

import httpx
from aiobotocore.config import AioConfig
from aiobotocore.session import get_session
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from types_aiobotocore_s3.client import S3Client

from amcat4.config import get_settings


class AmcatConnections:
    db: AsyncConnectionPool[Any] | None
    s3_client: S3Client | None
    s3_context_stack: AsyncExitStack | None
    http_client: httpx.AsyncClient | None

    def __init__(
        self,
        db: AsyncConnectionPool[Any] | None = None,
        s3_client: S3Client | None = None,
        s3_proxy_client: S3Client | None = None,
        s3_context_stack: AsyncExitStack | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.db = db
        self.s3_client = s3_client
        self.s3_proxy_client = s3_client
        self.s3_context_stack = s3_context_stack
        self.http_client = http_client


CONNECTIONS = AmcatConnections(s3_client=None, s3_proxy_client=None, db=None, http_client=None)  # type: ignore


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
        await _start_db()
        await _start_http()
        yield
    finally:
        await _close_s3()
        await _close_db()
        await _close_http()


def db() -> AsyncConnectionPool[Any]:
    """
    Access the postgres connection pool. Use amcat4.postgres.connection.connection() to get a connection.
    """
    if CONNECTIONS.db is None:
        raise ConnectionError("Database connection not initialized")
    return CONNECTIONS.db


def db_schema() -> str:
    """The postgres schema that contains the amcat tables (a separate schema is used for unit tests)"""
    settings = get_settings()
    return f"{settings.postgres_schema}_test" if settings.test_mode else settings.postgres_schema


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


async def _start_db():
    settings = get_settings()
    logging.debug(f"Connecting with postgres, schema {db_schema()}")
    pool = AsyncConnectionPool(
        settings.postgres_url,
        min_size=1,
        max_size=20,
        open=False,
        kwargs={"row_factory": dict_row, "autocommit": True, "options": f"-c search_path={db_schema()},public"},
    )
    try:
        await pool.open(wait=True, timeout=10)
    except Exception as e:
        await pool.close()
        raise ConnectionError(f"Cannot connect to postgres server: {e}") from e
    CONNECTIONS.db = pool


async def _close_db() -> None:
    if CONNECTIONS.db is not None:
        await CONNECTIONS.db.close()
        CONNECTIONS.db = None


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
