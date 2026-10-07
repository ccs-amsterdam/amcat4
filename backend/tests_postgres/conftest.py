"""
Tests for the experimental postgres backend.

These tests need a postgres server with pg_search, e.g.:
    docker run -d -p 5433:5432 -e POSTGRES_USER=amcat -e POSTGRES_PASSWORD=amcat -e POSTGRES_DB=amcat paradedb/paradedb
    AMCAT4_POSTGRES_TEST_URL=postgresql://amcat:amcat@localhost:5433/amcat uv run pytest tests_postgres

Pure unit tests (query parsing, snippets) run without a database.
"""

import os

import pytest
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from amcat4.postgres.schema import create_schema, drop_schema

TEST_URL = os.environ.get("AMCAT4_POSTGRES_TEST_URL")


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def conn():
    if not TEST_URL:
        pytest.skip("AMCAT4_POSTGRES_TEST_URL not set")
    async with await AsyncConnection.connect(TEST_URL, row_factory=dict_row, autocommit=True) as c:
        await drop_schema(c)
        await create_schema(c)
        yield c
        await drop_schema(c)
