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
    - text_fields:   tokenized full-text fields (BM25, with positions for phrase queries)
    - exact_fields:  untokenized fields (keyword, tag, url, number, integer, boolean, date, geo_point, multimedia
                     paths), stored as fast (columnar) fields for filtering, sorting and aggregation
    - stored_fields: values that are stored but not indexed (object)
- Vectors are stored in the document_vectors table (pgvector), with a vector index per field.
- A BM25 index covers partition_id, project_pk, the standard columns, text_fields and exact_fields. New fields are
  new json keys, so adding a field never requires rebuilding the index.
- The documents table is list partitioned on partition_id, and every partition has its own BM25 index. Every project
  is assigned to a partition when it is created (projects.partition_id): the newest partition, until its BM25 index
  reaches partition_max_gb, after which a new partition is created. So the long tail of small projects shares
  partitions, and a big project fills (most of) a partition. (Later: moving big projects to their own partition.)
  Queries on a project only use its own partition, but only if they have a SQL condition on partition_id: postgres
  does not know that a project is in one partition (see project_filter). partition_id is also in the BM25 index:
  pg_search checks SQL conditions on columns outside the index against the table, for every match. A foreign key
  keeps the documents of a project in its partition: updating projects.partition_id moves the documents.
  After mass updates, the index of a single partition can be rebuilt (amcat4 optimize --reindex --project ...).
- BM25 scores (how rare a word is) are computed per partition, so other projects in the same partition affect the
  ranking (but not which documents match).
- Standard metadata columns: date and source (e.g. publication date and outlet), which most communication data has.
  pg_search cannot sort on json keys inside the index (Top-K), so each project can map one date field to the date
  column and one keyword field to the source column (fields.sort_slot): real columns that are also in the index.
  Sorting on these fields is fast; sorting on other fields works but needs to read all matches. The first date
  field, and a keyword field called "source", are mapped automatically. Adding a standard column later means
  rebuilding the BM25 indexes.
- copied_from records the original project and document of copied documents.
- Date fields also get derived keys (f12_year, f12_month, f12_dayofweek, ...) in exact_fields, so date histograms
  and date-part filters run inside the index.

TODO (later): read-only *reference* projects, that reference documents owned by other projects
(project_references / document_references tables). Querying a reference project filters on the owner
project ids inside the BM25 index and then joins on the referenced document ids. Not implemented yet.
"""

import logging

from psycopg import AsyncConnection, sql
from psycopg.errors import LockNotAvailable

from amcat4.config import get_settings

# Key of the advisory lock that serializes assigning partitions (so two new projects cannot both create one)
_PARTITION_LOCK = 4_000_001


def partition_table(partition_id: int) -> str:
    return f"documents_p{partition_id}"


async def partition_of(conn: AsyncConnection, project_pk: int) -> int:
    """The documents partition of a project"""
    cur = await conn.execute("SELECT partition_id FROM projects WHERE pk = %s", [project_pk])
    row = await cur.fetchone()
    if row is None:
        raise ValueError(f"Project {project_pk} does not exist")
    return row["partition_id"]  # type: ignore[index, call-overload]


async def project_filter(conn: AsyncConnection, project_pk: int, table: str = "documents") -> sql.Composable:
    """
    SQL condition that selects the documents of a project. This includes the partition: postgres can only skip the
    other partitions if the query has a condition on the partition key.
    """
    return sql.SQL("{t}.partition_id = {part} AND {t}.project_pk = {pk}").format(
        t=sql.Identifier(table), part=sql.Literal(await partition_of(conn, project_pk)), pk=sql.Literal(project_pk)
    )


async def list_partitions(conn: AsyncConnection) -> list[dict]:
    """The documents partitions, with their table, BM25 index and sizes (sizes are cheap: no data is read)"""
    cur = await conn.execute(
        r"""SELECT (regexp_match(pg_get_expr(part.relpartbound, part.oid), 'IN \((\d+)\)'))[1]::int AS partition_id,
                   part.relname AS table, idx.relname AS index,
                   pg_relation_size(idx.oid) AS index_bytes, pg_total_relation_size(part.oid) AS total_bytes,
                   greatest(part.reltuples, 0)::bigint AS estimated_documents
            FROM pg_inherits i
            JOIN pg_class part ON part.oid = i.inhrelid
            JOIN pg_index ix ON ix.indrelid = part.oid
            JOIN pg_class idx ON idx.oid = ix.indexrelid
            JOIN pg_am am ON am.oid = idx.relam AND am.amname = 'bm25'
            WHERE i.inhparent = 'documents'::regclass
            ORDER BY 1"""
    )
    return await cur.fetchall()  # type: ignore[return-value]


async def partition_overview(conn: AsyncConnection) -> list[dict]:
    """
    The documents partitions with their sizes, and the projects in each partition with their number of documents.
    Counting documents reads the (document id) index of all partitions, so this takes a moment on large databases.
    """
    cur = await conn.execute(
        """SELECT p.partition_id, p.id AS project, coalesce(c.n, 0) AS documents
           FROM projects p
           LEFT JOIN (SELECT partition_id, project_pk, count(*) AS n FROM documents GROUP BY 1, 2) c
             ON c.partition_id = p.partition_id AND c.project_pk = p.pk
           ORDER BY documents DESC, project"""
    )
    projects: dict[int, list[dict]] = {}
    for row in await cur.fetchall():
        projects.setdefault(row["partition_id"], []).append({"project": row["project"], "documents": row["documents"]})  # type: ignore[index, call-overload]
    result = []
    for partition in await list_partitions(conn):
        members = projects.get(partition["partition_id"], [])
        result.append(
            {
                "partition_id": partition["partition_id"],
                "table": partition["table"],
                "index_bytes": partition["index_bytes"],
                "total_bytes": partition["total_bytes"],
                "documents": sum(p["documents"] for p in members),
                "projects": members,
            }
        )
    return result


async def create_partition(conn: AsyncConnection, partition_id: int, lock_timeout: str = "5s") -> None:
    """
    Create a new (empty) documents partition. Postgres creates its BM25 and other indexes when it is attached.
    CREATE TABLE ... PARTITION OF would need an exclusive lock on documents (waiting for, and blocking, all
    queries), so the table is created separately and then attached, which does not block queries or uploads.
    Raises LockNotAvailable if the lock cannot be acquired within lock_timeout.
    """
    table = sql.Identifier(partition_table(partition_id))
    async with conn.transaction():
        await conn.execute(sql.SQL("SET LOCAL lock_timeout = {}").format(sql.Literal(lock_timeout)))
        await conn.execute(sql.SQL("CREATE TABLE {} (LIKE documents INCLUDING DEFAULTS)").format(table))
        await conn.execute(
            sql.SQL("ALTER TABLE documents ATTACH PARTITION {} FOR VALUES IN ({})").format(table, sql.Literal(partition_id))
        )
        await conn.execute("SET LOCAL lock_timeout = DEFAULT")


async def assign_partition(conn: AsyncConnection) -> int:
    """
    The partition for a new project: the newest partition, or a new one if the BM25 index of the newest partition
    has reached partition_max_gb. Call this in the transaction that creates the project.
    Projects are never moved automatically: moving rewrites all documents of the project (and locks them).
    """
    await conn.execute("SELECT pg_advisory_xact_lock(%s)", [_PARTITION_LOCK])
    newest = (await list_partitions(conn))[-1]
    if newest["index_bytes"] < get_settings().partition_max_gb * 1024**3:
        return newest["partition_id"]
    partition_id = newest["partition_id"] + 1
    try:
        await create_partition(conn, partition_id)
    except LockNotAvailable:
        logging.warning(f"Could not create documents partition {partition_id} (lock timeout), using the current one")
        return newest["partition_id"]
    return partition_id


async def drop_schema(conn: AsyncConnection, schema: str) -> None:
    """Drop the amcat schema and ALL its data. Only for tests and benchmarks!"""
    await conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
