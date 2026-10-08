"""Initial schema (the schema of AmCAT before migrations were introduced)

Revision ID: 0001
Revises:
Create Date: 2026-10-08

Uses IF NOT EXISTS, so that databases created before migrations were introduced are upgraded cleanly.
"""

from typing import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = [
    """
    CREATE TABLE IF NOT EXISTS server_settings (
        id boolean PRIMARY KEY DEFAULT true CHECK (id),
        settings jsonb NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
        pk integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        id text NOT NULL UNIQUE,
        name text,
        description text,
        folder text,
        contact jsonb,
        image jsonb,
        archived timestamptz,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS roles (
        email text NOT NULL,
        project_pk integer REFERENCES projects(pk) ON DELETE CASCADE,  -- NULL for server roles
        role text NOT NULL
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS roles_unique ON roles (coalesce(project_pk, 0), email)",
    "CREATE INDEX IF NOT EXISTS roles_email ON roles (email)",
    """
    CREATE TABLE IF NOT EXISTS api_keys (
        id text PRIMARY KEY DEFAULT gen_random_uuid()::text,
        email text NOT NULL,
        name text NOT NULL,
        hashed_key text NOT NULL UNIQUE,
        expires_at timestamptz NOT NULL,
        jkt text,
        restrictions jsonb NOT NULL DEFAULT '{}'
    )
    """,
    "CREATE INDEX IF NOT EXISTS api_keys_email ON api_keys (email)",
    """
    CREATE TABLE IF NOT EXISTS requests (
        id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        type text NOT NULL,
        email text NOT NULL,
        project_pk integer REFERENCES projects(pk) ON DELETE CASCADE,  -- for project role requests
        new_project_id text,  -- for create project requests
        status text NOT NULL,
        timestamp timestamptz NOT NULL,
        request jsonb NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS requests_unique
        ON requests (type, email, coalesce(project_pk, 0), coalesce(new_project_id, ''))
    """,
    """
    CREATE TABLE IF NOT EXISTS object_storage (
        project_pk integer NOT NULL REFERENCES projects(pk) ON DELETE CASCADE,
        field text NOT NULL,
        filepath text NOT NULL,
        path text NOT NULL,
        size bigint NOT NULL,
        content_type text,
        registered timestamptz,
        last_synced timestamptz,
        PRIMARY KEY (project_pk, field, filepath)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fields (
        pk integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        project_pk integer NOT NULL REFERENCES projects(pk) ON DELETE CASCADE,
        name text NOT NULL,
        type text NOT NULL,
        unique_field boolean NOT NULL DEFAULT false,
        metareader jsonb NOT NULL DEFAULT '{}',
        reader jsonb NOT NULL DEFAULT '{}',
        client_settings jsonb NOT NULL DEFAULT '{}',
        sort_slot text,
        UNIQUE (project_pk, name),
        UNIQUE (project_pk, sort_slot)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS documents (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        project_pk integer NOT NULL REFERENCES projects(pk) ON DELETE CASCADE,
        doc_id text NOT NULL,
        dedup_hash text,  -- hash of the values of the unique fields of the project
        text_data jsonb NOT NULL DEFAULT '{}',
        meta_data jsonb NOT NULL DEFAULT '{}',
        extra_data jsonb,
        source jsonb,
        sort_date timestamptz,
        sort_number double precision,
        sort_keyword text COLLATE "C",
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (project_pk, doc_id)
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS documents_dedup ON documents (project_pk, dedup_hash) WHERE dedup_hash IS NOT NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS documents_bm25 ON documents USING bm25 (
        id,
        project_pk,
        sort_date,
        sort_number,
        (sort_keyword::pdb.literal),
        (text_data::pdb.unicode_words),
        (meta_data::pdb.literal)
    ) WITH (mutable_segment_rows = 0)
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id text PRIMARY KEY,
        type text NOT NULL,
        status text NOT NULL,  -- pending, running, done, failed, cancelled
        project_pk integer REFERENCES projects(pk) ON DELETE CASCADE,
        created_by text,
        params jsonb NOT NULL DEFAULT '{}',
        progress jsonb NOT NULL DEFAULT '{}',
        result jsonb,
        error text,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS jobs_status ON jobs (status)",
    """
    CREATE TABLE IF NOT EXISTS document_vectors (
        document_id bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        field_pk integer NOT NULL REFERENCES fields(pk) ON DELETE CASCADE,
        embedding public.vector NOT NULL,
        PRIMARY KEY (field_pk, document_id)
    )
    """,
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
    for statement in TABLES:
        op.execute(statement)
    # Replaced by alembic's version table
    op.execute("DROP TABLE IF EXISTS schema_version")


def downgrade() -> None:
    for table in [
        "document_vectors",
        "jobs",
        "documents",
        "fields",
        "object_storage",
        "requests",
        "api_keys",
        "roles",
        "projects",
        "server_settings",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table}")
