"""
Automatic maintenance of the BM25 indexes of the documents partitions.

Every upload adds segments to the index of a partition (pg_search does not seem to merge them), and updates leave
deleted documents in the index. Both make searches slower: rebuilding the index (REINDEX, online) fixes that and
is cheap (seconds per million documents), but rebuilding while a partition is still changing is wasted work.

So a periodic task (check_partitions, run by the job worker) looks at every partition:
- whether it changed since the previous check (postgres counts inserts, updates and deletes per table)
- whether its index needs a rebuild: many more segments than after the previous rebuild, or many deleted documents
If a partition needs a rebuild and has been quiet for QUIET_PERIOD (or has needed one for MAX_WAIT, for partitions
that are never quiet), it creates a reindex job. Only one reindex job exists at a time.
"""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from amcat4.postgres.connection import connection, fetch_all, fetch_one
from amcat4.postgres.layout import drop_reindex_leftovers, index_segments, list_partitions, partition_changes, reindex

if TYPE_CHECKING:
    from amcat4.projects.jobs import Job

CHECK_INTERVAL = timedelta(minutes=5)
QUIET_PERIOD = timedelta(minutes=15)
MAX_WAIT = timedelta(hours=24)
MIN_SEGMENTS = 16  # a rebuild gives up to ~one segment per parallel worker; small indexes have fewer
MAX_DELETED = 0.2  # fraction of the documents in the index


def needs_reindex(segments: dict, segments_after_rebuild: int | None) -> str | None:
    """The reason why an index needs a rebuild (or None)"""
    if segments["deleted"] > MAX_DELETED * max(segments["documents"], 1):
        return f"{segments['deleted']} deleted documents"
    if segments["segments"] > max(MIN_SEGMENTS, 2 * (segments_after_rebuild or 0)):
        return f"{segments['segments']} segments"
    return None


async def _segments_after_rebuild() -> dict[int, int]:
    """The number of segments after the last (automatic) rebuild of each partition"""
    rows = await fetch_all(
        """SELECT DISTINCT ON (params->>'partition_id') (params->>'partition_id')::int AS partition_id,
                  (result->>'segments_after')::int AS segments
           FROM jobs WHERE type = 'reindex' AND status = 'done'
           ORDER BY params->>'partition_id', updated_at DESC"""
    )
    return {row["partition_id"]: row["segments"] for row in rows}


async def check_partitions(state: dict, now: datetime | None = None) -> dict:
    """
    Periodic task: create a reindex job for a partition that needs it (see module docstring).
    state contains, per partition, the number of changes seen in the previous check, when it last changed, and
    since when it needs a rebuild.
    """
    from amcat4.projects.jobs import create_job

    now = now or datetime.now(UTC)
    if await fetch_one("SELECT 1 FROM jobs WHERE type = 'reindex' AND status IN ('pending', 'running')"):
        return state
    async with connection() as conn:
        await drop_reindex_leftovers(conn)
        changes = await partition_changes(conn)
        partitions = await list_partitions(conn)
        segments = {p["partition_id"]: await index_segments(conn, p["index"]) for p in partitions}
    after_rebuild = await _segments_after_rebuild()

    seen = state.get("partitions", {})
    new_state: dict[str, dict] = {}
    due = []
    for p in partitions:
        pid = p["partition_id"]
        previous = seen.get(str(pid), {})
        n = changes.get(p["table"], 0)
        changed_at = previous.get("changed_at") if previous.get("changes") == n else now.isoformat()
        reason = needs_reindex(segments[pid], after_rebuild.get(pid))
        needed_since = (previous.get("needed_since") or now.isoformat()) if reason else None
        new_state[str(pid)] = {"changes": n, "changed_at": changed_at, "needed_since": needed_since}
        if reason and (
            now - datetime.fromisoformat(changed_at) >= QUIET_PERIOD or now - datetime.fromisoformat(needed_since) >= MAX_WAIT  # type: ignore[arg-type]
        ):
            due.append((segments[pid]["segments"], pid, reason))
    if due:
        _, pid, reason = max(due)
        await create_job("reindex", None, None, {"partition_id": pid, "reason": reason})
    return {"partitions": new_state}


async def reindex_job(job: "Job") -> dict:
    """Job: rebuild the BM25 index of a partition (params: partition_id)"""
    partition_id = job.params["partition_id"]
    async with connection() as conn:
        partition = next((p for p in await list_partitions(conn) if p["partition_id"] == partition_id), None)
        if partition is None:
            raise ValueError(f"Partition {partition_id} does not exist")
        before = await index_segments(conn, partition["index"])
        started = datetime.now(UTC)
        await reindex(conn, partition["index"])
        seconds = (datetime.now(UTC) - started).total_seconds()
        after = await index_segments(conn, partition["index"])
    return {
        "partition_id": partition_id,
        "seconds": round(seconds, 1),
        "segments_before": before["segments"],
        "segments_after": after["segments"],
        "deleted_before": before["deleted"],
    }
