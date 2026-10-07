from contextlib import asynccontextmanager
from typing import AsyncGenerator

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from amcat4.config import get_settings

_POOL: AsyncConnectionPool | None = None


async def start_postgres(url: str | None = None, min_size: int = 1, max_size: int = 10) -> AsyncConnectionPool:
    global _POOL
    url = url or get_settings().postgres_url
    if not url:
        raise ConnectionError("No postgres_url configured")
    _POOL = AsyncConnectionPool(url, min_size=min_size, max_size=max_size, open=False, kwargs={"row_factory": dict_row})
    await _POOL.open(wait=True)
    return _POOL


async def close_postgres() -> None:
    global _POOL
    if _POOL is not None:
        await _POOL.close()
        _POOL = None


def pool() -> AsyncConnectionPool:
    if _POOL is None:
        raise ConnectionError("Postgres connection pool not initialized")
    return _POOL


@asynccontextmanager
async def connection() -> AsyncGenerator[AsyncConnection, None]:
    async with pool().connection() as conn:
        yield conn
