import pytest
from psycopg import sql

from amcat4.models import ProjectSettings
from amcat4.postgres.connection import connection
from amcat4.postgres.layout import list_partitions, partition_of, partition_table
from amcat4.postgres.projects import project_pk
from amcat4.postgres.search import SearchQuery, compile_search
from amcat4.projects.index import create_project_index, delete_project_index
from amcat4.systemdata.fields import get_fieldset
from tests.conftest import upload
from tests.tools import amcat_settings, get_json


async def _partition(index: str) -> dict:
    async with connection() as conn:
        partition_id = await partition_of(conn, await project_pk(index))
        return next(p for p in await list_partitions(conn) if p["partition_id"] == partition_id)


async def _tables(index: str) -> list[str]:
    async with connection() as conn:
        cur = await conn.execute(
            "SELECT DISTINCT tableoid::regclass::text AS t FROM documents WHERE project_pk = %s", [await project_pk(index)]
        )
        return [row["t"] for row in await cur.fetchall()]  # type: ignore[index, call-overload]


async def _count(index: str, q: str) -> int:
    c = compile_search(await get_fieldset(index), SearchQuery(queries={"q": q}))
    async with connection() as conn:
        cur = await conn.execute(sql.SQL("SELECT count(*) AS n FROM documents WHERE {}").format(c.where), c.params)
        return (await cur.fetchone())["n"]  # type: ignore[index]


@pytest.mark.anyio
async def test_documents_in_project_partition(index_docs):
    partition = await _partition(index_docs)
    assert await _tables(index_docs) == [partition["table"]]
    assert partition["index"].startswith(partition["table"])


@pytest.mark.anyio
async def test_search_uses_one_partition(index_docs):
    partition = await _partition(index_docs)
    c = compile_search(await get_fieldset(index_docs), SearchQuery(queries={"q": "test"}))
    async with connection() as conn:
        cur = await conn.execute(sql.SQL("EXPLAIN SELECT id FROM documents WHERE {}").format(c.where), c.params)
        plan = "\n".join(next(iter(row.values())) for row in await cur.fetchall())
    scanned = {line.split(" on ")[1].split()[0] for line in plan.splitlines() if " on documents_p" in line}
    assert scanned == {partition["table"]}


@pytest.mark.anyio
async def test_reindex(index_docs):
    partition = await _partition(index_docs)
    async with connection() as conn:
        for statement in [
            sql.SQL("VACUUM ANALYZE {}").format(sql.Identifier(partition["table"])),
            sql.SQL("REINDEX INDEX CONCURRENTLY {}").format(sql.Identifier(partition["index"])),
            sql.SQL("REINDEX INDEX CONCURRENTLY documents_bm25"),  # all partitions
        ]:
            await conn.execute(statement)
    assert await _count(index_docs, "test") == 2


@pytest.mark.anyio
async def test_new_partition_when_full(index_docs):
    """If the newest partition is full, a new project gets a new partition (with its own BM25 index)"""
    index = "amcat4_unittest_newpartition"
    await delete_project_index(index, ignore_missing=True)
    old = await _partition(index_docs)
    try:
        with amcat_settings(partition_max_gb=0):
            await create_project_index(ProjectSettings(id=index))
        new = await _partition(index)
        assert new["partition_id"] > old["partition_id"]
        assert new["table"] == partition_table(new["partition_id"])
        await upload(index, [{"title": "new", "text": "a test document"}], fields={"title": "text", "text": "text"})
        assert await _tables(index) == [new["table"]]
        assert await _count(index, "test") == 1
        assert await _count(index_docs, "test") == 2
        # the next project goes to the new partition, which is not full yet
        await delete_project_index(index)
        await create_project_index(ProjectSettings(id=index))
        assert (await _partition(index))["partition_id"] == new["partition_id"]
    finally:
        await delete_project_index(index, ignore_missing=True)


@pytest.mark.anyio
async def test_move_project(index_docs):
    """Changing the partition of a project moves its documents (moving is not in the API yet)"""
    index = "amcat4_unittest_moveproject"
    await delete_project_index(index, ignore_missing=True)
    try:
        with amcat_settings(partition_max_gb=0):
            await create_project_index(ProjectSettings(id=index))
        target = (await _partition(index))["partition_id"]
        async with connection() as conn:
            await conn.execute("UPDATE projects SET partition_id = %s WHERE id = %s", [target, index_docs])
        assert await _tables(index_docs) == [partition_table(target)]
        assert await _count(index_docs, "test") == 2
    finally:
        await delete_project_index(index, ignore_missing=True)


@pytest.mark.anyio
async def test_partitions_api(client, index_docs, admin, writer):
    await get_json(client, "/partitions", user=writer, expected=403)
    result = await get_json(client, "/partitions", user=admin)
    assert result["max_index_bytes"] > 0
    partition = next(p for p in result["partitions"] if any(x["project"] == index_docs for x in p["projects"]))
    assert partition["index_bytes"] > 0
    assert {"project": index_docs, "documents": 4} in partition["projects"]
