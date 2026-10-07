"""
Database schema for the PostgreSQL (pg_search) backend.

Design (see docs/postgres-migration.md for the reasoning):

- All documents of all projects live in a single `documents` table. A project owns its documents.
- Document values are stored in jsonb columns, keyed by a stable *field key* (e.g. "f12") rather than the
  field name. Field names are project-level labels in the `fields` table, so renaming a field is a metadata
  update, and two projects can use the same name with different types.
- Values are split over columns by how they need to be indexed:
    - text_data:  tokenized full-text fields (BM25, with positions for phrase queries)
    - meta_data:  untokenized fields (keyword, tag, url, number, integer, boolean, date, multimedia paths),
                  stored as fast (columnar) fields for filtering, sorting and aggregation
    - extra_data: values that are stored but not indexed (object, vector, geo_point for now)
- A single BM25 index covers project_pk, sort_date, text_data and meta_data. New fields are new json keys, so
  adding a field never requires rebuilding the index.
- pg_search cannot sort on json keys inside the index (Top-K), so the primary date field of each project is also
  stored in the sort_date column. Date fields also get derived keys (f12_year, f12_month, f12_dayofweek, ...) in
  meta_data, so date histograms and date-part filters run inside the index.

TODO (later): read-only *reference* projects, that reference documents owned by other projects
(project_references / document_references tables). Querying a reference project filters on the owner
project ids inside the BM25 index and then joins on the referenced document ids. Not implemented yet.
"""

from psycopg import AsyncConnection

SCHEMA_VERSION = 1

SCHEMA_SQL = [
    "CREATE EXTENSION IF NOT EXISTS pg_search",
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version integer NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
        pk integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        id text NOT NULL UNIQUE,
        name text,
        description text,
        archived timestamptz,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fields (
        pk integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        project_pk integer NOT NULL REFERENCES projects(pk) ON DELETE CASCADE,
        name text NOT NULL,
        type text NOT NULL,
        unique_field boolean NOT NULL DEFAULT false,
        primary_date boolean NOT NULL DEFAULT false,
        metareader jsonb NOT NULL DEFAULT '{"access": "none"}',
        client_settings jsonb NOT NULL DEFAULT '{}',
        UNIQUE (project_pk, name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS documents (
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        project_pk integer NOT NULL REFERENCES projects(pk) ON DELETE CASCADE,
        doc_id text NOT NULL,
        dedup_hash bytea,
        text_data jsonb NOT NULL DEFAULT '{}',
        meta_data jsonb NOT NULL DEFAULT '{}',
        extra_data jsonb,
        source jsonb,
        sort_date timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (project_pk, doc_id)
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS documents_dedup
        ON documents (project_pk, dedup_hash) WHERE dedup_hash IS NOT NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS documents_bm25 ON documents USING bm25 (
        id,
        project_pk,
        sort_date,
        (text_data::pdb.unicode_words),
        (meta_data::pdb.literal)
    )
    """,
]


async def create_schema(conn: AsyncConnection) -> None:
    async with conn.transaction():
        for statement in SCHEMA_SQL:
            await conn.execute(statement)  # type: ignore[arg-type]
        cur = await conn.execute("SELECT version FROM schema_version")
        if await cur.fetchone() is None:
            await conn.execute("INSERT INTO schema_version (version) VALUES (%s)", [SCHEMA_VERSION])


async def drop_schema(conn: AsyncConnection) -> None:
    """Drop all amcat tables. Only for tests and benchmarks!"""
    async with conn.transaction():
        for table in ["documents", "fields", "projects", "schema_version"]:
            await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")  # type: ignore[arg-type]
