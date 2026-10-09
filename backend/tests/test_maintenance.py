from datetime import UTC, datetime, timedelta

import pytest

from amcat4.models import ProjectSettings
from amcat4.postgres.connection import connection, execute, fetch_all
from amcat4.postgres.layout import index_segments, list_partitions, partition_of
from amcat4.postgres.projects import project_pk
from amcat4.projects import jobs, maintenance
from amcat4.projects.index import create_project_index, delete_project_index
from tests.conftest import upload


@pytest.fixture
async def clean_jobs():
    await execute("DELETE FROM jobs WHERE type = 'reindex'")
    await execute("DELETE FROM periodic_tasks")
    yield
    await execute("DELETE FROM jobs WHERE type = 'reindex'")
    await execute("DELETE FROM periodic_tasks")


@pytest.mark.anyio
async def test_needs_reindex():
    assert maintenance.needs_reindex({"segments": 10, "documents": 100, "deleted": 0}, None) is None
    assert maintenance.needs_reindex({"segments": 20, "documents": 100, "deleted": 0}, None) == "20 segments"
    assert maintenance.needs_reindex({"segments": 50, "documents": 100, "deleted": 0}, 30) is None
    assert maintenance.needs_reindex({"segments": 61, "documents": 100, "deleted": 0}, 30) == "61 segments"
    assert maintenance.needs_reindex({"segments": 1, "documents": 100, "deleted": 30}, None) == "30 deleted documents"


@pytest.mark.anyio
async def test_periodic_tasks(clean_jobs, monkeypatch):
    calls = []

    async def task(state: dict) -> dict:
        calls.append(state)
        return {"n": state.get("n", 0) + 1}

    monkeypatch.setattr(jobs, "PERIODIC", {"test": jobs.PeriodicTask(interval=timedelta(hours=1), run=task)})
    assert await jobs.run_periodic_tasks() == ["test"]
    assert await jobs.run_periodic_tasks() == []  # not due yet
    await execute("UPDATE periodic_tasks SET last_run = now() - interval '2 hours'")
    assert await jobs.run_periodic_tasks() == ["test"]
    assert calls == [{}, {"n": 1}]  # the state is kept between runs


@pytest.mark.anyio
async def test_reindex_when_quiet(clean_jobs):
    index = "amcat4_unittest_maintenance"
    await delete_project_index(index, ignore_missing=True)
    try:
        await create_project_index(ProjectSettings(id=index))
        for i in range(maintenance.MIN_SEGMENTS + 1):  # every upload adds a segment
            await upload(index, [{"text": f"document {i}"}], fields={"text": "text"})
        async with connection() as conn:
            partition_id = await partition_of(conn, await project_pk(index))
            partition = next(p for p in await list_partitions(conn) if p["partition_id"] == partition_id)
            assert (await index_segments(conn, partition["index"]))["segments"] > maintenance.MIN_SEGMENTS

        def reindex_jobs():
            return fetch_all("SELECT status, params, result FROM jobs WHERE type = 'reindex'")

        # the partition just changed: wait until it is quiet
        t0 = datetime.now(UTC)
        state = await maintenance.check_partitions({}, now=t0)
        assert await reindex_jobs() == []
        state = await maintenance.check_partitions(state, now=t0 + timedelta(minutes=5))
        assert await reindex_jobs() == []
        state = await maintenance.check_partitions(state, now=t0 + maintenance.QUIET_PERIOD + timedelta(minutes=1))
        [job] = await reindex_jobs()
        assert job["status"] == "pending" and job["params"]["partition_id"] == partition_id

        assert await jobs.run_pending_jobs() == 1
        [job] = await reindex_jobs()
        assert job["status"] == "done"
        assert job["result"]["segments_after"] < job["result"]["segments_before"]

        # after the rebuild, the partition doesn't need another one
        await maintenance.check_partitions(state, now=t0 + timedelta(hours=1))
        assert len(await reindex_jobs()) == 1
    finally:
        await delete_project_index(index, ignore_missing=True)


@pytest.mark.anyio
async def test_reindex_if_never_quiet(clean_jobs):
    """A partition that keeps changing is rebuilt anyway once it needed a rebuild for MAX_WAIT"""
    index = "amcat4_unittest_maintenance"
    await delete_project_index(index, ignore_missing=True)
    try:
        await create_project_index(ProjectSettings(id=index))
        for i in range(maintenance.MIN_SEGMENTS + 1):
            await upload(index, [{"text": f"document {i}"}], fields={"text": "text"})
        t0 = datetime.now(UTC)
        state = await maintenance.check_partitions({}, now=t0)
        await upload(index, [{"text": "another document"}], fields={"text": "text"})
        await maintenance.check_partitions(state, now=t0 + maintenance.MAX_WAIT + timedelta(minutes=1))
        assert len(await fetch_all("SELECT 1 FROM jobs WHERE type = 'reindex'")) == 1
    finally:
        await delete_project_index(index, ignore_missing=True)
