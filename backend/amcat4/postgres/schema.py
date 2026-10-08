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

The tables are created and changed by the (alembic) migrations in amcat4/migrations/versions.

TODO (later): read-only *reference* projects, that reference documents owned by other projects
(project_references / document_references tables). Querying a reference project filters on the owner
project ids inside the BM25 index and then joins on the referenced document ids. Not implemented yet.
"""

from psycopg import AsyncConnection, sql


async def drop_schema(conn: AsyncConnection, schema: str) -> None:
    """Drop the amcat schema and ALL its data. Only for tests and benchmarks!"""
    await conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
