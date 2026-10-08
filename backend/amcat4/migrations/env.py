"""
Alembic environment: runs the migrations in versions/ on the amcat schema.

Migrations are plain SQL (op.execute), there are no SQLAlchemy models. They are run at startup (see
amcat4.systemdata.manage), or manually with the alembic command line from the backend directory, e.g.:

    uv run alembic revision --rev-id 0002 -m "add priority to jobs"   # create a new migration in versions/
    uv run alembic upgrade head

Use sequential revision ids (0002, 0003, ...) rather than alembic's default random ids, so the files sort in order.
"""

from alembic import context
from sqlalchemy import create_engine, text

from amcat4.config import get_settings
from amcat4.connections import db_schema

# Arbitrary key for the advisory lock that makes sure only one process runs migrations at a time
MIGRATION_LOCK = 4_000_001


def sqlalchemy_url(url: str) -> str:
    """Use the psycopg (3) driver: plain postgresql:// urls would make SQLAlchemy look for psycopg2"""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


def run_migrations() -> None:
    schema = context.config.attributes.get("schema") or db_schema()
    engine = create_engine(sqlalchemy_url(get_settings().postgres_url))
    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_LOCK})
        try:
            # The schema has to exist before alembic can create its version table in it
            quoted = conn.dialect.identifier_preparer.quote(schema)
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {quoted}"))
            conn.execute(text(f"SET search_path TO {quoted}, public"))
            conn.commit()
            context.configure(connection=conn, version_table_schema=schema)
            with context.begin_transaction():
                context.run_migrations()
            conn.commit()
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK})
            conn.commit()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline (sql script) migrations are not supported")
run_migrations()
