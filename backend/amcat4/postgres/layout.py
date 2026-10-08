"""
Storage layout of AmCAT on PostgreSQL + pg_search: the design of the database, and helpers that inspect it.

The tables themselves are not defined here, but in the (alembic) migrations in amcat4/migrations/versions:
0001_initial.py contains the complete initial schema, and later migrations change it. Migrations are history and
must never be edited once released, so this module is the place for the (current) design and its rationale.

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
- A BM25 index covers project_pk, the sort slots, text_data and meta_data. New fields are new json keys, so
  adding a field never requires rebuilding the index.
- The documents table is hash partitioned on project_pk (64 partitions), and every partition has its own BM25 index.
  Queries on a project only use its own partition (queries must have a SQL condition on project_pk for this).
  After mass updates, the index of a single partition can be rebuilt (amcat4 optimize --reindex --project ...).
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


async def document_partition(conn: AsyncConnection, project_pk: int) -> tuple[str, str]:
    """The names of the documents partition that contains the documents of this project, and of its BM25 index"""
    cur = await conn.execute(
        r"""SELECT part.relname AS partition, idx.relname AS index
            FROM pg_inherits i
            JOIN pg_class part ON part.oid = i.inhrelid
            JOIN pg_index ix ON ix.indrelid = part.oid
            JOIN pg_class idx ON idx.oid = ix.indexrelid
            JOIN pg_am am ON am.oid = idx.relam AND am.amname = 'bm25',
            LATERAL regexp_match(pg_get_expr(part.relpartbound, part.oid), 'modulus (\d+), remainder (\d+)') m
            WHERE i.inhparent = 'documents'::regclass
              AND satisfies_hash_partition('documents'::regclass, m[1]::int, m[2]::int, %s::int)""",
        [project_pk],
    )
    row = await cur.fetchone()
    if row is None:
        raise ValueError(f"No documents partition found for project {project_pk}")
    return row["partition"], row["index"]  # type: ignore[index, call-overload]


async def drop_schema(conn: AsyncConnection, schema: str) -> None:
    """Drop the amcat schema and ALL its data. Only for tests and benchmarks!"""
    await conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
