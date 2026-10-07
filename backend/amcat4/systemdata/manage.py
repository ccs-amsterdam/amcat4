"""
Creating and managing the database schema.

Future schema changes should be implemented as migrations from SCHEMA_VERSION n to n+1 in create_schema.
"""

from amcat4.connections import db_schema
from amcat4.postgres.connection import connection
from amcat4.postgres.schema import SCHEMA_VERSION, create_schema, drop_schema


async def create_or_update_systemdata(rm_pending_migrations: bool = True) -> int:
    """
    Create the database schema if needed. Call this at startup.
    :return: The active schema version.
    """
    async with connection() as conn:
        await create_schema(conn, db_schema())
    return SCHEMA_VERSION


async def delete_systemdata_version(version: int | None = None) -> None:
    """
    DANGER: drop the whole amcat schema, including all projects and documents.
    """
    async with connection() as conn:
        await drop_schema(conn, db_schema())
