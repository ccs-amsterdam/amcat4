"""
Creating and managing the database schema.

The schema is created and updated by the alembic migrations in amcat4/migrations/versions.
To change the schema, add a migration (see amcat4/migrations/env.py).
"""

import asyncio

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from amcat4.connections import db_schema
from amcat4.postgres.connection import connection
from amcat4.postgres.schema import drop_schema


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", "amcat4:migrations")
    config.attributes["schema"] = db_schema()
    return config


async def create_or_update_systemdata() -> str:
    """
    Create the database schema or upgrade it to the latest version. Call this at startup.
    :return: The active schema version (alembic revision).
    """
    config = _alembic_config()
    # alembic is synchronous, so run it in a thread to not block the event loop
    await asyncio.to_thread(command.upgrade, config, "head")
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head


async def delete_systemdata() -> None:
    """
    DANGER: drop the whole amcat schema, including all projects and documents.
    """
    async with connection() as conn:
        await drop_schema(conn, db_schema())
