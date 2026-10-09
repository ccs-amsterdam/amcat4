"""
Benchmark for the postgres (pg_search) backend.

Creates a synthetic corpus with a skewed project size distribution (one big project, some medium ones, many
small ones), loads it with the normal upload code, and times typical AmCAT operations via the same functions
the API uses.

Usage (uses a separate postgres schema 'amcat_benchmark', which is dropped and recreated):
    AMCAT4_POSTGRES_URL=postgresql://amcat:amcat@localhost:5432/amcat uv run python benchmark/pg_benchmark.py --scale 1.0

Scale 1.0 = 1M documents of ~150 words.
"""

import argparse
import asyncio
import json
import os
import random
import statistics
import time
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

os.environ["AMCAT4_POSTGRES_SCHEMA"] = "amcat_benchmark"

import amcat4.connections  # noqa: E402
from amcat4.connections import amcat_connections  # noqa: E402
from amcat4.models import FieldSpec, FilterSpec, ProjectSettings, SnippetParams, UpdateDocumentField  # noqa: E402
from amcat4.postgres.connection import connection, fetch_one  # noqa: E402
from amcat4.projects.aggregate import Axis, query_aggregate  # noqa: E402
from amcat4.projects.documents import create_or_update_documents  # noqa: E402
from amcat4.projects.index import create_project_index  # noqa: E402
from amcat4.projects.jobs import create_job, get_job, run_pending_jobs  # noqa: E402
from amcat4.projects.query import query_documents, update_tag_query  # noqa: E402
from amcat4.systemdata.fields import create_fields, update_fields  # noqa: E402
from amcat4.systemdata.manage import create_or_update_systemdata, delete_systemdata  # noqa: E402

FIELD_TYPES: dict[str, Any] = {
    "title": "text",
    "text": "text",
    "source": "keyword",
    "date": "date",
    "n": "integer",
    "tags": "tag",
}
SOURCES = [f"source_{i}" for i in range(25)]
TAGS = [f"tag{i}" for i in range(40)]
WORDS_PER_DOC = 150


class _SerialPool(amcat4.connections.AsyncConnectionPool):
    """
    Connection pool without parallel query. pg_search estimates the number of matches from the largest index segment
    (https://github.com/paradedb/paradedb/issues/6563), and postgres decides on parallel workers based on that
    estimate. So the number of workers would depend on the index layout, making the phases incomparable.
    """

    def __init__(self, *args, **kwargs):
        kwargs["kwargs"]["options"] += " -c max_parallel_workers_per_gather=0"
        super().__init__(*args, **kwargs)


amcat4.connections.AsyncConnectionPool = _SerialPool  # type: ignore[misc]

results: dict[str, Any] = {}


def make_vocabulary(n: int = 30000, seed: int = 1) -> tuple[list[str], list[float]]:
    rng = random.Random(seed)
    syllables = ["ka", "lo", "mi", "ne", "ru", "sa", "ti", "vo", "ze", "pa", "do", "gi", "fu", "be", "xo", "wy"]
    vocab: set[str] = set()
    while len(vocab) < n:
        vocab.add("".join(rng.choice(syllables) for _ in range(rng.randint(2, 4))))
    words = sorted(vocab)
    rng.shuffle(words)
    cum, total = [], 0.0
    for rank in range(n):
        total += 1 / (rank + 1) ** 1.07
        cum.append(total)
    return words, cum


VOCAB, CUM = make_vocabulary()
COMMON = VOCAB[3]  # appears in almost every document
RARE, MEDIUM = "zzrareword", "zzmediumword"  # planted in 0.05% and 2% of documents


def make_doc(rng: random.Random) -> dict:
    words = rng.choices(VOCAB, cum_weights=CUM, k=WORDS_PER_DOC)
    r = rng.random()
    if r < 0.0005:
        words[rng.randrange(len(words))] = RARE
    if r < 0.02:
        words[rng.randrange(len(words))] = MEDIUM
    date = datetime(2000, 1, 1) + timedelta(seconds=rng.randrange(25 * 365 * 24 * 3600))
    doc: dict[str, Any] = dict(
        title=" ".join(rng.choices(VOCAB, cum_weights=CUM, k=8)).capitalize(),
        text=" ".join(words),
        source=rng.choice(SOURCES),
        date=date,
        n=rng.randrange(1000),
    )
    if rng.random() < 0.5:
        doc["tags"] = rng.sample(TAGS, rng.randint(1, 3))
    return doc


async def timeit(label: str, fn: Callable[[], Awaitable[Any]], repeat: int = 5) -> Any:
    out = await fn()  # warm-up
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        out = await fn()
        times.append((time.perf_counter() - t0) * 1000)
    results[label] = {"median_ms": round(statistics.median(times), 1), "max_ms": round(max(times), 1)}
    print(f"{label:70s} {statistics.median(times):9.1f} ms  (max {max(times):.1f})")
    return out


async def load(scale: float) -> None:
    projects = {"big": int(500_000 * scale)}
    projects.update({f"medium_{i}": int(15_000 * scale) for i in range(20)})
    projects.update({f"small_{i}": max(10, int(250 * scale)) for i in range(800)})
    for name in projects:
        await create_project_index(ProjectSettings(id=name))
        await create_fields(name, FIELD_TYPES)

    queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
    for name, n in projects.items():
        for start in range(0, n, 5000):
            queue.put_nowait((name, min(5000, n - start)))
    total = sum(projects.values())
    print(f"Loading {total} documents in {len(projects)} projects")

    async def worker(seed: int):
        rng = random.Random(seed)
        while not queue.empty():
            name, n = queue.get_nowait()
            await create_or_update_documents(name, [make_doc(rng) for _ in range(n)])

    t0 = time.perf_counter()
    await asyncio.gather(*(worker(i) for i in range(4)))
    elapsed = time.perf_counter() - t0
    results["load"] = {"documents": total, "seconds": round(elapsed, 1), "docs_per_second": round(total / elapsed)}
    print(f"Loaded in {elapsed:.0f}s ({total / elapsed:.0f} docs/s, including generating the documents)")


PHASES = ["after upload", "after upload + reindex", "after mass update", "after mass update + reindex"]


def q(query=None):
    return {"q": query} if query else None


async def sizes() -> dict:
    row = await fetch_one(
        # documents and its BM25 index are partitioned: sum the sizes of the partitions
        """SELECT pg_size_pretty((SELECT sum(pg_table_size(relid)) FROM pg_partition_tree('documents'))) AS table_incl_toast,
                  pg_size_pretty((SELECT sum(pg_relation_size(relid)) FROM pg_partition_tree('documents_bm25'))) AS bm25_index,
                  pg_size_pretty((SELECT sum(pg_total_relation_size(relid)) FROM pg_partition_tree('documents'))) AS total"""
    )
    assert row is not None
    return row


async def reads(phase: str) -> None:
    """The read operations, measured in every phase (labels get the phase as suffix)"""
    fields = [FieldSpec(name="title"), FieldSpec(name="date")]

    async def t(label, fn, **kargs):
        return await timeit(f"{label} [{phase}]", fn, **kargs)

    print("--- search (10 results incl. total count)")
    for project in ["big", "medium_0", "small_0"]:
        for label, term in [("rare", RARE), ("medium", MEDIUM), ("common", COMMON)]:
            await t(
                f"search {label} term in {project}",
                lambda p=project, term=term: query_documents(p, fields=fields, queries=q(term)),
            )
    medium = [f"medium_{i}" for i in range(20)]
    await t("search common term in 20 medium projects", lambda: query_documents(medium, fields=fields, queries=q(COMMON)))
    await t(
        "boolean query in big",
        lambda: query_documents("big", fields=fields, queries=q(f'({MEDIUM} OR "{COMMON} {VOCAB[10]}"~5) AND NOT {RARE}')),
    )
    await t("prefix query (zzmed*) in big", lambda: query_documents("big", fields=fields, queries=q("zzmed*")))

    print("--- filters and sorting")
    f = {"date": FilterSpec(gte="2010-01-01", lt="2011-01-01"), "source": FilterSpec(values=["source_1", "source_2"])}
    await t("date range + keyword filter in big", lambda: query_documents("big", fields=fields, filters=f))
    await t("monthnr filter in big", lambda: query_documents("big", fields=fields, filters={"date": FilterSpec(monthnr=3)}))
    date_desc = [{"date": {"order": "desc"}}]
    source_desc = [{"source": {"order": "desc"}}]
    await t("sort by date (date column), no query, big", lambda: query_documents("big", fields=fields, sort=date_desc))  # type: ignore
    await t(
        "sort by date (date column), common query, big",
        lambda: query_documents("big", fields=fields, queries=q(COMMON), sort=date_desc),  # type: ignore
    )
    await t("sort by source (source column), big", lambda: query_documents("big", fields=fields, sort=source_desc))  # type: ignore
    await t(
        "page 1000 (offset 10000), common query, big",
        lambda: query_documents("big", fields=fields, queries=q(COMMON), page=1000),
    )

    print("--- snippets")
    snippet = [FieldSpec(name="title"), FieldSpec(name="text", snippet=SnippetParams(nomatch_words=20, max_matches=3))]
    await t(
        "medium query in big, 100 results with snippets",
        lambda: query_documents("big", fields=snippet, queries=q(MEDIUM), per_page=100),
    )

    print("--- aggregation")
    await t("terms(source), all docs in big", lambda: query_aggregate("big", [Axis("source")]))
    await t("month histogram, all docs in big", lambda: query_aggregate("big", [Axis("date", "month")]))
    await t("month histogram, medium query in big", lambda: query_aggregate("big", [Axis("date", "month")], queries=q(MEDIUM)))
    await t(
        "year x source, common query in big",
        lambda: query_aggregate("big", [Axis("date", "year"), Axis("source")], queries=q(COMMON)),
    )
    await t("tags terms, all docs in big", lambda: query_aggregate("big", [Axis("tags")]))


async def maintenance(label: str, *statements: str) -> None:
    t0 = time.perf_counter()
    async with connection() as conn:
        for statement in statements:
            await conn.execute(statement)  # type: ignore[arg-type]
    results[label] = {"seconds": round(time.perf_counter() - t0, 1)}
    print(f"{label}: {results[label]['seconds']}s")


def print_comparison() -> None:
    """Median times (ms) of the read operations per phase"""
    labels = [k.rsplit(" [", 1)[0] for k in results if k.endswith(f"[{PHASES[0]}]")]
    print(f"\n{'operation':55s}" + "".join(f"{p:>30s}" for p in PHASES))
    for label in labels:
        row = [results.get(f"{label} [{p}]", {}).get("median_ms") for p in PHASES]
        print(f"{label:55s}" + "".join(f"{v:30.1f}" if v is not None else f"{'-':>30s}" for v in row))


async def segments() -> int:
    """Number of segments of the BM25 index (of all partitions)"""
    row = await fetch_one(
        """SELECT count(*) AS n FROM pg_partition_tree('documents_bm25') t, paradedb.index_info(t.relid)
           WHERE t.isleaf"""
    )
    return row["n"] if row else 0


async def phase(name: str) -> None:
    results[f"sizes {name}"] = {**await sizes(), "segments": await segments()}
    print(f"\n=== {name}: {results[f'sizes {name}']}")
    await reads(name)


async def benchmark() -> None:
    # VACUUM (which autovacuum also does) updates the statistics; it does not merge BM25 index segments
    await maintenance("vacuum after upload", "VACUUM ANALYZE documents")
    await phase(PHASES[0])
    # rebuild the index online, as `amcat4 optimize --reindex` does
    await maintenance("reindex after upload", "REINDEX INDEX CONCURRENTLY documents_bm25")
    await phase(PHASES[1])

    # A mass update: unmapping and remapping the source column rewrites all documents of big (twice). This is what
    # happens on e.g. tagging all documents or changing a field type. In between, sort on source without the column.
    fields = [FieldSpec(name="title"), FieldSpec(name="date")]
    print("\n=== mass update of big")
    t0 = time.perf_counter()
    await update_fields("big", {"source": UpdateDocumentField(fast_sort=False)})
    results["unmap source (updates all rows of big)"] = {"seconds": round(time.perf_counter() - t0, 1)}
    await timeit(
        "sort by source (not mapped: reads all rows), big",
        lambda: query_documents("big", fields=fields, sort=[{"source": {"order": "desc"}}]),  # type: ignore
        repeat=2,
    )
    t0 = time.perf_counter()
    await update_fields("big", {"source": UpdateDocumentField(fast_sort=True)})
    results["map source (updates all rows of big)"] = {"seconds": round(time.perf_counter() - t0, 1)}
    print(
        f"unmap + map source: {results['unmap source (updates all rows of big)']['seconds']}s + "
        f"{results['map source (updates all rows of big)']['seconds']}s"
    )
    await maintenance("vacuum after mass update", "VACUUM ANALYZE documents")
    await phase(PHASES[2])
    await maintenance("reindex after mass update", "REINDEX INDEX CONCURRENTLY documents_bm25")
    await phase(PHASES[3])
    print_comparison()

    print("\n--- writes")
    t0 = time.perf_counter()
    res = await update_tag_query("big", "add", "tags", "benchmark", queries=q(MEDIUM))
    results["add tag by query in big"] = {"documents": res["updated"], "seconds": round(time.perf_counter() - t0, 2)}
    print(f"add tag to {res['updated']} documents: {time.perf_counter() - t0:.2f}s")
    await create_project_index(ProjectSettings(id="copy"))
    t0 = time.perf_counter()
    job = await create_job("copy", "copy", None, dict(source="big", destination="copy", queries=q(MEDIUM)))
    await run_pending_jobs()
    copied = (await get_job(job["id"]))["result"]["copied"]
    results["copy subset of big"] = {"documents": copied, "seconds": round(time.perf_counter() - t0, 2)}
    print(f"copy {copied} documents to new project: {time.perf_counter() - t0:.2f}s")
    rng = random.Random(99)
    await timeit(
        "upload 100 docs into small project",
        lambda: create_or_update_documents("small_0", [make_doc(rng) for _ in range(100)]),
    )


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--output", default="benchmark/benchmark_results.json")
    args = parser.parse_args()
    async with amcat_connections():
        await delete_systemdata()
        await create_or_update_systemdata()
        await load(args.scale)
        if not os.environ.get("BENCHMARK_LOAD_ONLY"):
            await benchmark()
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, default=str)


if __name__ == "__main__":
    asyncio.run(main())
