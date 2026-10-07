from contextlib import asynccontextmanager
from typing import AsyncGenerator

from psycopg import AsyncConnection

from amcat4.connections import db


@asynccontextmanager
async def connection() -> AsyncGenerator[AsyncConnection, None]:
    """
    Get a connection from the pool. Connections are in autocommit mode; use `async with conn.transaction()`
    for statements that need to be atomic.
    """
    async with db().connection() as conn:
        yield conn


async def execute(query, params=None) -> int:
    """Execute a statement on a pooled connection, returning the number of affected rows"""
    async with connection() as conn:
        cur = await conn.execute(query, params)
        return cur.rowcount


async def fetch_all(query, params=None) -> list[dict]:
    async with connection() as conn:
        cur = await conn.execute(query, params)
        return await cur.fetchall()  # type: ignore[return-value]


async def fetch_one(query, params=None) -> dict | None:
    async with connection() as conn:
        cur = await conn.execute(query, params)
        return await cur.fetchone()  # type: ignore[return-value]
