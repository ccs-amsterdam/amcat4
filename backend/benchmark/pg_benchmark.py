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


async def benchmark() -> None:
    t0 = time.perf_counter()
    async with connection() as conn:
        await conn.execute("VACUUM ANALYZE documents")  # also merges BM25 index segments
    results["vacuum_seconds"] = round(time.perf_counter() - t0, 1)
    row = await fetch_one(
        # documents and its BM25 index are partitioned: sum the sizes of the partitions
        """SELECT pg_size_pretty((SELECT sum(pg_table_size(relid)) FROM pg_partition_tree('documents'))) AS table_incl_toast,
                  pg_size_pretty((SELECT sum(pg_relation_size(relid)) FROM pg_partition_tree('documents_bm25'))) AS bm25_index,
                  pg_size_pretty((SELECT sum(pg_total_relation_size(relid)) FROM pg_partition_tree('documents'))) AS total"""
    )
    results["sizes"] = row
    print(f"VACUUM: {results['vacuum_seconds']}s. Sizes: {row}")

    def q(query=None):
        return {"q": query} if query else None

    fields = [FieldSpec(name="title"), FieldSpec(name="date")]

    print("\n--- search (10 results incl. total count)")
    for project in ["big", "medium_0", "small_0"]:
        for label, term in [("rare", RARE), ("medium", MEDIUM), ("common", COMMON)]:
            res = await timeit(
                f"search {label} term in {project}",
                lambda p=project, t=term: query_documents(p, fields=fields, queries=q(t)),
            )
            results[f"search {label} term in {project}"]["hits"] = res.total_count if res else 0
    medium = [f"medium_{i}" for i in range(20)]
    await timeit("search common term in 20 medium projects", lambda: query_documents(medium, fields=fields, queries=q(COMMON)))
    await timeit(
        "boolean query in big",
        lambda: query_documents("big", fields=fields, queries=q(f'({MEDIUM} OR "{COMMON} {VOCAB[10]}"~5) AND NOT {RARE}')),
    )
    await timeit("prefix query (zzmed*) in big", lambda: query_documents("big", fields=fields, queries=q("zzmed*")))

    print("\n--- filters and sorting")
    f = {"date": FilterSpec(gte="2010-01-01", lt="2011-01-01"), "source": FilterSpec(values=["source_1", "source_2"])}
    await timeit("date range + keyword filter in big", lambda: query_documents("big", fields=fields, filters=f))
    await timeit(
        "monthnr filter in big", lambda: query_documents("big", fields=fields, filters={"date": FilterSpec(monthnr=3)})
    )
    date_desc = [{"date": {"order": "desc"}}]
    await timeit("sort by date (sort slot), no query, big", lambda: query_documents("big", fields=fields, sort=date_desc))  # type: ignore
    await timeit(
        "sort by date (sort slot), common query, big",
        lambda: query_documents("big", fields=fields, queries=q(COMMON), sort=date_desc),  # type: ignore
    )
    n_desc = [{"n": {"order": "desc"}}]
    await timeit("sort by number (no sort slot), big", lambda: query_documents("big", fields=fields, sort=n_desc), repeat=2)  # type: ignore
    t0 = time.perf_counter()
    await update_fields("big", {"n": UpdateDocumentField(fast_sort=True)})
    results["put n in sort slot (updates all rows of big)"] = {"seconds": round(time.perf_counter() - t0, 1)}
    # updating all rows leaves dead rows and index entries; rebuild the index (online), see `amcat4 optimize --reindex`
    t0 = time.perf_counter()
    async with connection() as conn:
        await conn.execute("VACUUM ANALYZE documents")
        await conn.execute("REINDEX INDEX CONCURRENTLY documents_bm25")
    results["vacuum + reindex after sort slot update"] = {"seconds": round(time.perf_counter() - t0, 1)}
    print(
        f"put n in sort slot: {results['put n in sort slot (updates all rows of big)']['seconds']}s, "
        f"vacuum + reindex: {results['vacuum + reindex after sort slot update']['seconds']}s"
    )
    await timeit("sort by number (sort slot), big", lambda: query_documents("big", fields=fields, sort=n_desc))  # type: ignore
    await timeit(
        "page 1000 (offset 10000), common query, big",
        lambda: query_documents("big", fields=fields, queries=q(COMMON), page=1000),
    )

    print("\n--- snippets")
    snippet = [FieldSpec(name="title"), FieldSpec(name="text", snippet=SnippetParams(nomatch_words=20, max_matches=3))]
    await timeit(
        "medium query in big, 100 results with snippets",
        lambda: query_documents("big", fields=snippet, queries=q(MEDIUM), per_page=100),
    )

    print("\n--- aggregation")
    await timeit("terms(source), all docs in big", lambda: query_aggregate("big", [Axis("source")]))
    await timeit("month histogram, all docs in big", lambda: query_aggregate("big", [Axis("date", "month")]))
    await timeit(
        "month histogram, medium query in big", lambda: query_aggregate("big", [Axis("date", "month")], queries=q(MEDIUM))
    )
    await timeit(
        "year x source, common query in big",
        lambda: query_aggregate("big", [Axis("date", "year"), Axis("source")], queries=q(COMMON)),
    )
    await timeit("tags terms, all docs in big", lambda: query_aggregate("big", [Axis("tags")]))

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
