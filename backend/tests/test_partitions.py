import pytest
from psycopg import sql

from amcat4.postgres.connection import connection
from amcat4.postgres.layout import document_partition
from amcat4.postgres.projects import project_pk
from amcat4.postgres.search import SearchQuery, compile_search
from amcat4.systemdata.fields import get_fieldset


@pytest.mark.anyio
async def test_document_partition(index_docs):
    pk = await project_pk(index_docs)
    async with connection() as conn:
        partition, index = await document_partition(conn, pk)
        cur = await conn.execute("SELECT DISTINCT tableoid::regclass::text AS t FROM documents WHERE project_pk = %s", [pk])
        assert [row["t"] for row in await cur.fetchall()] == [partition]
        assert index.startswith(partition)


@pytest.mark.anyio
async def test_search_uses_one_partition(index_docs):
    pk = await project_pk(index_docs)
    c = compile_search(await get_fieldset(index_docs), SearchQuery(queries={"q": "test"}))
    async with connection() as conn:
        partition, _ = await document_partition(conn, pk)
        cur = await conn.execute(sql.SQL("EXPLAIN SELECT id FROM documents WHERE {}").format(c.where), c.params)
        plan = "\n".join(next(iter(row.values())) for row in await cur.fetchall())
    scanned = {line.split(" on ")[1].split()[0] for line in plan.splitlines() if " on documents_p" in line}
    assert scanned == {partition}


@pytest.mark.anyio
async def test_reindex(index_docs):
    pk = await project_pk(index_docs)
    async with connection() as conn:
        partition, index = await document_partition(conn, pk)
        for statement in [
            sql.SQL("VACUUM ANALYZE {}").format(sql.Identifier(partition)),
            sql.SQL("REINDEX INDEX CONCURRENTLY {}").format(sql.Identifier(index)),
            sql.SQL("REINDEX INDEX CONCURRENTLY documents_bm25"),  # all partitions
        ]:
            await conn.execute(statement)
    c = compile_search(await get_fieldset(index_docs), SearchQuery(queries={"q": "test"}))
    async with connection() as conn:
        cur = await conn.execute(sql.SQL("SELECT count(*) AS n FROM documents WHERE {}").format(c.where), c.params)
        assert (await cur.fetchone())["n"] == 2  # type: ignore[index]
