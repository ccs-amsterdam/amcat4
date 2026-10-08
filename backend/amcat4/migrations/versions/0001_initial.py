"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-08

The documents table is hash partitioned on project_pk, so each partition has its own (smaller) BM25 index:
queries on a project only use the index of its partition, and an index can be rebuilt (after mass updates) one
partition at a time. See amcat4/postgres/layout.py for the design.
"""

from typing import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Changing the number of partitions later means rewriting the whole documents table
DOCUMENT_PARTITIONS = 64

TABLES = [
    """
    CREATE TABLE server_settings (
        id boolean PRIMARY KEY DEFAULT true CHECK (id),
        settings jsonb NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE projects (
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
    CREATE TABLE roles (
        email text NOT NULL,
        project_pk integer REFERENCES projects(pk) ON DELETE CASCADE,  -- NULL for server roles
        role text NOT NULL
    )
    """,
    "CREATE UNIQUE INDEX roles_unique ON roles (coalesce(project_pk, 0), email)",
    "CREATE INDEX roles_email ON roles (email)",
    """
    CREATE TABLE api_keys (
        id text PRIMARY KEY DEFAULT gen_random_uuid()::text,
        email text NOT NULL,
        name text NOT NULL,
        hashed_key text NOT NULL UNIQUE,
        expires_at timestamptz NOT NULL,
        jkt text,
        restrictions jsonb NOT NULL DEFAULT '{}'
    )
    """,
    "CREATE INDEX api_keys_email ON api_keys (email)",
    """
    CREATE TABLE requests (
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
    CREATE UNIQUE INDEX requests_unique
        ON requests (type, email, coalesce(project_pk, 0), coalesce(new_project_id, ''))
    """,
    """
    CREATE TABLE object_storage (
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
    CREATE TABLE fields (
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
    CREATE TABLE documents (
        id bigint GENERATED ALWAYS AS IDENTITY,
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
        -- unique constraints on a partitioned table must include the partition key
        PRIMARY KEY (id, project_pk),
        UNIQUE (project_pk, doc_id)
    ) PARTITION BY HASH (project_pk)
    """,
    *[
        f"CREATE TABLE documents_p{i:02} PARTITION OF documents FOR VALUES WITH (MODULUS {DOCUMENT_PARTITIONS}, REMAINDER {i})"
        for i in range(DOCUMENT_PARTITIONS)
    ],
    """
    CREATE UNIQUE INDEX documents_dedup ON documents (project_pk, dedup_hash) WHERE dedup_hash IS NOT NULL
    """,
    # Creates a BM25 index on every partition
    """
    CREATE INDEX documents_bm25 ON documents USING bm25 (
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
    CREATE TABLE jobs (
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
    "CREATE INDEX jobs_status ON jobs (status)",
    """
    CREATE TABLE document_vectors (
        document_id bigint NOT NULL,
        project_pk integer NOT NULL,  -- needed for the foreign key to the (partitioned) documents table
        field_pk integer NOT NULL REFERENCES fields(pk) ON DELETE CASCADE,
        embedding public.vector NOT NULL,
        PRIMARY KEY (field_pk, document_id),
        FOREIGN KEY (document_id, project_pk) REFERENCES documents(id, project_pk) ON DELETE CASCADE
    )
    """,
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
    for statement in TABLES:
        op.execute(statement)


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
        op.execute(f"DROP TABLE {table}")
