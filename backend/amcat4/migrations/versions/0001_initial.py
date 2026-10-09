"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-08

The documents table is list partitioned on partition_id, so each partition has its own (smaller) BM25 index:
queries on a project only use the index of its partition, and an index can be rebuilt (after mass updates) one
partition at a time. Every project is assigned to a partition when it is created; new partitions are created when
the current one is full. See amcat4/postgres/layout.py for the design.
"""

from typing import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
        created_at timestamptz NOT NULL DEFAULT now(),
        partition_id integer NOT NULL,  -- the documents partition of the project
        UNIQUE (pk, partition_id)  -- for the foreign key from documents
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
        partition_id integer NOT NULL,
        project_pk integer NOT NULL,
        doc_id text NOT NULL,
        dedup_hash text,  -- hash of the values of the unique fields of the project
        text_fields jsonb NOT NULL DEFAULT '{}',
        exact_fields jsonb NOT NULL DEFAULT '{}',
        stored_fields jsonb,
        copied_from jsonb,  -- {project_pk, doc_id} of the original, for copied documents
        -- standard metadata columns: a project can map one of its fields to each (for fast sorting)
        date timestamptz,
        source text COLLATE "C",
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        -- unique constraints on a partitioned table must include the partition key
        PRIMARY KEY (id, partition_id),
        UNIQUE (partition_id, project_pk, doc_id),
        -- documents are always in the partition of their project (moving a project cascades to its documents)
        FOREIGN KEY (project_pk, partition_id) REFERENCES projects(pk, partition_id) ON UPDATE CASCADE ON DELETE CASCADE
    ) PARTITION BY LIST (partition_id)
    """,
    # More partitions are created when needed (amcat4.postgres.layout.assign_partition)
    "CREATE TABLE documents_p1 PARTITION OF documents FOR VALUES IN (1)",
    """
    CREATE UNIQUE INDEX documents_dedup ON documents (partition_id, project_pk, dedup_hash) WHERE dedup_hash IS NOT NULL
    """,
    # Creates a BM25 index on every partition
    """
    CREATE INDEX documents_bm25 ON documents USING bm25 (
        id,
        project_pk,
        date,
        (source::pdb.literal),
        (text_fields::pdb.unicode_words),
        (exact_fields::pdb.literal)
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
        partition_id integer NOT NULL,  -- needed for the foreign key to the (partitioned) documents table
        field_pk integer NOT NULL REFERENCES fields(pk) ON DELETE CASCADE,
        embedding public.vector NOT NULL,
        PRIMARY KEY (field_pk, document_id),
        FOREIGN KEY (document_id, partition_id) REFERENCES documents(id, partition_id) ON UPDATE CASCADE ON DELETE CASCADE
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
