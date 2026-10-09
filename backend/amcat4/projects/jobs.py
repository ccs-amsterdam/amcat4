"""
Background jobs.

Jobs are stored in the jobs table. A worker loop (started with the API server, see job_worker) claims pending jobs
with FOR UPDATE SKIP LOCKED, so multiple server processes can run jobs safely. Job handlers work in batches and
store their progress after every batch, so a job that was interrupted (e.g. by a server restart) continues where it
left off: running jobs that have not been updated for a while are claimed again.

While a job runs, a heartbeat keeps updated_at current, so long steps (e.g. rebuilding an index) are not mistaken
for interrupted jobs.

Periodic tasks are quick checks that run every interval (e.g. "does a partition need a reindex?", or later "are
outsourced tasks done?"). The worker loop runs them too; the periodic_tasks table makes sure each task runs at most
once per interval across all server processes, and keeps its state between runs. Periodic tasks should be quick:
for heavy work, they create a job.

To add a new job type, write an async handler (job: Job) -> result dict and register it in HANDLERS.
To add a periodic task, write an async function (state: dict) -> new state dict and register it in PERIODIC.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Awaitable, Callable

from psycopg import sql
from psycopg.types.json import Jsonb

from amcat4.errors import NotFoundError
from amcat4.models import CreateDocumentField, FieldType, FilterSpec
from amcat4.postgres import documents as storage
from amcat4.postgres.connection import connection, execute, fetch_all, fetch_one
from amcat4.postgres.fields import FieldSet
from amcat4.postgres.projects import project_partitions, project_pk
from amcat4.postgres.search import SearchQuery, compile_search
from amcat4.projects import maintenance

BATCH_SIZE = 2000
STALE_AFTER = "2 minutes"  # running jobs that were not updated for this long are considered interrupted
HEARTBEAT_SECONDS = 30

_COLUMNS = (
    "id, type, status, (SELECT id FROM projects WHERE pk = jobs.project_pk) AS project, created_by, params, "
    "progress, result, error, created_at, updated_at"
)


class JobCancelled(Exception):
    pass


@dataclass
class Job:
    id: str
    type: str
    params: dict
    progress: dict

    async def save_progress(self, **progress) -> None:
        """Store progress (and check whether the job was cancelled)"""
        self.progress.update(progress)
        row = await fetch_one(
            "UPDATE jobs SET progress = %s, updated_at = now() WHERE id = %s RETURNING status", [Jsonb(self.progress), self.id]
        )
        if row is None or row["status"] == "cancelled":
            raise JobCancelled()


async def create_job(type: str, project: str | None, created_by: str | None, params: dict) -> dict:
    if type not in HANDLERS:
        raise ValueError(f"Unknown job type {type}")
    job_id = uuid.uuid4().hex
    pk = await project_pk(project) if project else None
    await execute(
        "INSERT INTO jobs (id, type, status, project_pk, created_by, params) VALUES (%s, %s, 'pending', %s, %s, %s)",
        [job_id, type, pk, created_by, Jsonb(params)],
    )
    return await get_job(job_id)


async def get_job(job_id: str) -> dict:
    row = await fetch_one(f"SELECT {_COLUMNS} FROM jobs WHERE id = %s", [job_id])  # type: ignore[arg-type]
    if row is None:
        raise NotFoundError(f"Job {job_id} does not exist")
    return row


async def list_jobs(project: str | None = None, created_by: str | None = None) -> list[dict]:
    conditions, params = ["TRUE"], []
    if project:
        conditions.append("project_pk = (SELECT pk FROM projects WHERE id = %s)")
        params.append(project)
    if created_by:
        conditions.append("created_by = %s")
        params.append(created_by)
    return await fetch_all(
        f"SELECT {_COLUMNS} FROM jobs WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT 100",
        params,  # type: ignore[arg-type]
    )


async def cancel_job(job_id: str) -> None:
    await execute(
        "UPDATE jobs SET status = 'cancelled', updated_at = now() WHERE id = %s AND status IN ('pending', 'running')", [job_id]
    )


async def _claim_job() -> Job | None:
    async with connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                f"""SELECT id, type, params, progress FROM jobs
                    WHERE status = 'pending' OR (status = 'running' AND updated_at < now() - interval '{STALE_AFTER}')
                    ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"""  # type: ignore[arg-type]
            )
            row = await cur.fetchone()
            if row is None:
                return None
            await conn.execute("UPDATE jobs SET status = 'running', updated_at = now() WHERE id = %s", [row["id"]])  # type: ignore[index, call-overload]
    return Job(id=row["id"], type=row["type"], params=row["params"], progress=row["progress"])  # type: ignore[index, call-overload]


async def _heartbeat(job_id: str) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        await execute("UPDATE jobs SET updated_at = now() WHERE id = %s AND status = 'running'", [job_id])


async def run_job(job: Job) -> None:
    heartbeat = asyncio.create_task(_heartbeat(job.id))
    try:
        result = await HANDLERS[job.type](job)
    except JobCancelled:
        logging.info(f"Job {job.id} was cancelled")
        return
    except Exception as e:
        logging.exception(f"Job {job.id} failed")
        await execute("UPDATE jobs SET status = 'failed', error = %s, updated_at = now() WHERE id = %s", [str(e), job.id])
        return
    finally:
        heartbeat.cancel()
    await execute(
        "UPDATE jobs SET status = 'done', result = %s, updated_at = now() WHERE id = %s AND status = 'running'",
        [Jsonb(result), job.id],
    )


async def run_pending_jobs() -> int:
    """Run all pending jobs (until none are left). Returns the number of jobs that were run."""
    n = 0
    while (job := await _claim_job()) is not None:
        await run_job(job)
        n += 1
    return n


@dataclass
class PeriodicTask:
    interval: timedelta
    run: Callable[[dict], Awaitable[dict]]


async def run_periodic_tasks() -> list[str]:
    """Run the periodic tasks that are due (and not already run by another process). Returns their names."""
    ran = []
    for name, task in PERIODIC.items():
        # claim the task: insert it, or update last_run if the interval has passed (atomic, so only one process wins)
        row = await fetch_one(
            """INSERT INTO periodic_tasks AS t (name, last_run) VALUES (%s, now())
               ON CONFLICT (name) DO UPDATE SET last_run = now() WHERE t.last_run <= now() - %s
               RETURNING state""",
            [name, task.interval],
        )
        if row is None:
            continue
        try:
            state = await task.run(row["state"])
        except Exception:
            logging.exception(f"Periodic task {name} failed")
            continue
        await execute("UPDATE periodic_tasks SET state = %s WHERE name = %s", [Jsonb(state), name])
        ran.append(name)
    return ran


async def job_worker(poll_interval: float = 2.0) -> None:
    """Run periodic tasks and jobs forever (started as a background task by the API server)"""
    while True:
        try:
            await run_periodic_tasks()
            await run_pending_jobs()
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Error in job worker")
        await asyncio.sleep(poll_interval)


###################### JOB TYPES ######################


async def _copy_job(job: Job) -> dict[str, Any]:
    """
    Copy documents (optionally a subset selected by queries/filters, and a subset of fields) to another project.
    params: source, destination, queries, filters, field_options
      field_options: per source field: {rename: str, exclude: bool, type: FieldType}
    """
    from amcat4.systemdata.fields import create_fields, field_infos, list_fields

    p = job.params
    from_pk, to_pk = await project_pk(p["source"]), await project_pk(p["destination"])

    if "field_map" not in job.progress:
        # Set up the destination fields (only once)
        field_options = p.get("field_options") or {}
        dest_fields = await list_fields(p["destination"])
        new_fields: dict[str, CreateDocumentField] = {}
        field_map: dict[str, str] = {}
        for name, definition in (await list_fields(p["source"])).items():
            opts = field_options.get(name, {})
            if opts.get("exclude"):
                continue
            dest_name = opts.get("rename") or name
            field_map[name] = dest_name
            if dest_name in dest_fields:
                continue
            type_override: FieldType | None = opts.get("type")
            if type_override and type_override != definition.type:
                new_fields[dest_name] = CreateDocumentField(type=type_override)
            else:
                new_fields[dest_name] = CreateDocumentField(
                    type=definition.type,
                    unique=definition.unique,
                    metareader=definition.metareader,
                    reader=definition.reader,
                    client_settings=definition.client_settings,
                )
        if new_fields:
            await create_fields(p["destination"], new_fields)
        source_infos = await field_infos(p["source"])
        query = SearchQuery(
            queries=p.get("queries"), filters={k: FilterSpec(**v) for k, v in (p.get("filters") or {}).items()} or None
        )
        c = compile_search(FieldSet({from_pk: source_infos}, partitions=await project_partitions([from_pk])), query)
        async with connection() as conn:
            cur = await conn.execute(sql.SQL("SELECT count(*) AS n FROM documents WHERE {}").format(c.where), c.params)
            total = (await cur.fetchone())["n"]  # type: ignore[index, call-overload]
        await job.save_progress(field_map=field_map, total=total, copied=0, after_id=0)

    source_infos = await field_infos(p["source"])
    dest_infos = await field_infos(p["destination"])
    field_map_infos = {source_infos[s]: dest_infos[d] for s, d in job.progress["field_map"].items()}
    query = SearchQuery(
        queries=p.get("queries"), filters={k: FilterSpec(**v) for k, v in (p.get("filters") or {}).items()} or None
    )
    c = compile_search(FieldSet({from_pk: source_infos}, partitions=await project_partitions([from_pk])), query)
    while True:
        async with connection() as conn:
            cur = await conn.execute(
                sql.SQL("SELECT id FROM documents WHERE {} AND documents.id > %s ORDER BY id LIMIT %s").format(c.where),
                [*c.params, job.progress["after_id"], BATCH_SIZE],
            )
            ids = [row["id"] for row in await cur.fetchall()]  # type: ignore[index, call-overload]
            if not ids:
                break
            n = await storage.copy_batch(conn, from_pk, to_pk, field_map_infos, dest_infos, ids)
        await job.save_progress(after_id=ids[-1], copied=job.progress["copied"] + n)
    return {"copied": job.progress["copied"]}


HANDLERS: dict[str, Callable[[Job], Awaitable[dict[str, Any]]]] = {
    "copy": _copy_job,
    "reindex": maintenance.reindex_job,
}

PERIODIC: dict[str, PeriodicTask] = {
    "partition_maintenance": PeriodicTask(interval=maintenance.CHECK_INTERVAL, run=maintenance.check_partitions),
}
