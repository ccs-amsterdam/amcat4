"""
Database schema for AmCAT on PostgreSQL + pg_search.

System data (projects, settings, roles, api keys, requests, object storage register) are plain tables.

Documents:
- All documents of all projects live in a single `documents` table. A project owns its documents.
- Document values are stored in jsonb columns, keyed by a stable *field key* (e.g. "f12") rather than the
  field name. Field names are project-level labels in the `fields` table, so renaming a field is a metadata
  update, and two projects can use the same name with different types.
- Values are split over columns by how they need to be indexed:
    - text_data:  tokenized full-text fields (BM25, with positions for phrase queries)
    - meta_data:  untokenized fields (keyword, tag, url, number, integer, boolean, date, geo_point, multimedia
                  paths), stored as fast (columnar) fields for filtering, sorting and aggregation
    - extra_data: values that are stored but not indexed (object)
- Vectors are stored in the document_vectors table (pgvector), with a vector index per field.
- A single BM25 index covers project_pk, the sort slots, text_data and meta_data. New fields are new json keys, so
  adding a field never requires rebuilding the index.
- pg_search cannot sort on json keys inside the index (Top-K), so each project can promote one date, one number
  and one keyword field to a *sort slot*: a real column (sort_date, sort_number, sort_keyword) that is also in the
  index. Sorting on a field in a sort slot is fast; sorting on other fields works but needs to read all matches.
  The first date field of a project gets the date slot automatically.
- Date fields also get derived keys (f12_year, f12_month, f12_dayofweek, ...) in meta_data, so date histograms
  and date-part filters run inside the index.

TODO (later): read-only *reference* projects, that reference documents owned by other projects
(project_references / document_references tables). Querying a reference project filters on the owner
project ids inside the BM25 index and then joins on the referenced document ids. Not implemented yet.
"""

from psycopg import AsyncConnection, sql

SCHEMA_VERSION = 1

TABLES = [
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version integer NOT NULL
    )
    """,
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
        role_context text NOT NULL,
        role text NOT NULL,
        PRIMARY KEY (role_context, email)
    )
    """,
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
        type text NOT NULL,
        email text NOT NULL,
        project_id text NOT NULL DEFAULT '',
        status text NOT NULL,
        timestamp timestamptz NOT NULL,
        request jsonb NOT NULL,
        PRIMARY KEY (type, email, project_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS object_storage (
        project_id text NOT NULL,
        field text NOT NULL,
        filepath text NOT NULL,
        path text NOT NULL,
        size bigint NOT NULL,
        content_type text,
        registered timestamptz,
        last_synced timestamptz,
        PRIMARY KEY (project_id, field, filepath)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fields (
        pk integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        project_pk integer NOT NULL REFERENCES projects(pk) ON DELETE CASCADE,
        name text NOT NULL,
        type text NOT NULL,
        elastic_type text NOT NULL,
        identifier boolean NOT NULL DEFAULT false,
        metareader jsonb NOT NULL DEFAULT '{"access": "none"}',
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
    CREATE INDEX IF NOT EXISTS documents_bm25 ON documents USING bm25 (
        id,
        project_pk,
        sort_date,
        sort_number,
        (sort_keyword::pdb.literal),
        (text_data::pdb.unicode_words),
        (meta_data::pdb.literal)
    )
    """,
    """
    CREATE UNLOGGED TABLE IF NOT EXISTS scrolls (
        id text PRIMARY KEY,
        params jsonb NOT NULL,
        position bigint,
        page integer NOT NULL DEFAULT 0,
        expires_at timestamptz NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS document_vectors (
        document_id bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        field_pk integer NOT NULL REFERENCES fields(pk) ON DELETE CASCADE,
        embedding public.vector NOT NULL,
        PRIMARY KEY (field_pk, document_id)
    )
    """,
]


async def create_schema(conn: AsyncConnection, schema: str) -> None:
    """Create the amcat schema and tables if they do not exist (idempotent)"""
    async with conn.transaction():
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_search")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        await conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        await conn.execute(sql.SQL("SET LOCAL search_path TO {}, public").format(sql.Identifier(schema)))
        for statement in TABLES:
            await conn.execute(statement)  # type: ignore[arg-type]
        cur = await conn.execute("SELECT version FROM schema_version")
        row = await cur.fetchone()
        if row is None:
            await conn.execute("INSERT INTO schema_version (version) VALUES (%s)", [SCHEMA_VERSION])
        elif list(row.values() if isinstance(row, dict) else row)[0] > SCHEMA_VERSION:  # type: ignore[union-attr]
            raise RuntimeError("The database was created by a newer version of AmCAT")


async def drop_schema(conn: AsyncConnection, schema: str) -> None:
    """Drop the amcat schema and ALL its data. Only for tests and benchmarks!"""
    await conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
