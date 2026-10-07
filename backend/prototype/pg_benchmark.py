"""
Benchmark for the postgres (pg_search) backend prototype.

Creates a synthetic corpus with a skewed project size distribution (one big project, some medium ones, many
small ones), loads it with the normal upload code, and times typical AmCAT operations.

Usage (WARNING: drops and recreates the amcat tables in the target database):
    uv run python prototype/pg_benchmark.py postgresql://amcat:amcat@localhost:5433/amcat --scale 1.0

Scale 1.0 = 1M documents of ~150 words.
"""

import argparse
import asyncio
import json
import random
import statistics
import time
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from amcat4.models import FilterSpec, SnippetParams
from amcat4.postgres.aggregate import Axis, aggregate
from amcat4.postgres.documents import copy_documents, update_tag_by_query, upload_documents
from amcat4.postgres.fields import FieldSet, create_fields
from amcat4.postgres.projects import create_project
from amcat4.postgres.schema import create_schema, drop_schema
from amcat4.postgres.search import SearchQuery, compile_search, count, search

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
    weights = [1 / (rank + 1) ** 1.07 for rank in range(n)]
    cum, total = [], 0.0
    for w in weights:
        total += w
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
    doc = dict(
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


async def load(url: str, scale: float) -> dict[str, int]:
    projects = {"big": int(500_000 * scale)}
    projects.update({f"medium_{i}": int(15_000 * scale) for i in range(20)})
    projects.update({f"small_{i}": max(10, int(250 * scale)) for i in range(800)})
    async with await AsyncConnection.connect(url, row_factory=dict_row, autocommit=True) as conn:
        await drop_schema(conn)
        await create_schema(conn)
        pks = {}
        for name in projects:
            pks[name] = await create_project(conn, name)
            await create_fields(conn, pks[name], FIELD_TYPES)

    queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
    batch = 5000
    for name, n in projects.items():
        for start in range(0, n, batch):
            queue.put_nowait((name, min(batch, n - start)))
    total = sum(projects.values())
    print(f"Loading {total} documents in {len(projects)} projects")

    async def worker(seed: int):
        rng = random.Random(seed)
        async with await AsyncConnection.connect(url, row_factory=dict_row, autocommit=True) as conn:
            from amcat4.postgres.fields import list_fields

            fields_cache: dict[int, Any] = {}
            while not queue.empty():
                name, n = queue.get_nowait()
                pk = pks[name]
                if pk not in fields_cache:
                    fields_cache[pk] = await list_fields(conn, pk)
                await upload_documents(conn, pk, [make_doc(rng) for _ in range(n)], fields_cache[pk])

    t0 = time.perf_counter()
    await asyncio.gather(*(worker(i) for i in range(4)))
    elapsed = time.perf_counter() - t0
    results["load"] = {"documents": total, "seconds": round(elapsed, 1), "docs_per_second": round(total / elapsed)}
    print(f"Loaded in {elapsed:.0f}s ({total / elapsed:.0f} docs/s, including generating the documents)")
    return pks


async def sizes(conn: AsyncConnection) -> None:
    cur = await conn.execute(
        """SELECT pg_size_pretty(pg_table_size('documents')) AS table_incl_toast,
                  pg_size_pretty(pg_relation_size('documents_bm25')) AS bm25_index,
                  pg_size_pretty(pg_total_relation_size('documents')) AS total,
                  (SELECT count(*) FROM documents) AS n"""
    )
    row = await cur.fetchone()
    results["sizes"] = row
    print("Sizes:", row)


async def benchmark(url: str, pks: dict[str, int]) -> None:
    async with await AsyncConnection.connect(url, row_factory=dict_row, autocommit=True) as conn:
        segments = await conn.execute("SELECT count(*) AS n FROM pdb.index_segments('documents_bm25')")
        before = (await segments.fetchone())["n"]  # type: ignore[index]
        t0 = time.perf_counter()
        await conn.execute("VACUUM ANALYZE documents")  # also merges BM25 index segments
        segments = await conn.execute("SELECT count(*) AS n FROM pdb.index_segments('documents_bm25')")
        after = (await segments.fetchone())["n"]  # type: ignore[index]
        results["vacuum"] = {"seconds": round(time.perf_counter() - t0, 1), "segments_before": before, "segments_after": after}
        print(f"VACUUM: {time.perf_counter() - t0:.1f}s, BM25 segments {before} -> {after}")
        await sizes(conn)

        from amcat4.postgres.fields import list_fields

        fs: dict[str, FieldSet] = {}
        for name in ["big", "medium_0", "small_0"]:
            fs[name] = FieldSet({pks[name]: await list_fields(conn, pks[name])})
        all_projects = FieldSet({pk: await list_fields(conn, pk) for pk in list(pks.values())[:21]})

        def q(project, query=None, filters=None):
            return SearchQuery(queries={"q": query} if query else None, filters=filters)

        print("\n--- search (10 results incl. total count)")
        for project in ["big", "medium_0", "small_0"]:
            for label, term in [("rare", RARE), ("medium", MEDIUM), ("common", COMMON)]:
                res = await timeit(
                    f"search {label} term in {project}",
                    lambda p=project, t=term: search(conn, fs[p], q(p, t), ["title", "date"]),
                )
                results[f"search {label} term in {project}"]["hits"] = res.total
        await timeit("search common term in 21 projects", lambda: search(conn, all_projects, q(None, COMMON), ["title"]))
        await timeit(
            "search common term in big, without total count",
            lambda: search(conn, fs["big"], q("big", COMMON), ["title"], with_total=False),
        )
        await timeit("count only, common term in big", lambda: count(conn, fs["big"], q("big", COMMON)))
        await timeit(
            "boolean query in big",
            lambda: search(conn, fs["big"], q("big", f'({MEDIUM} OR "{COMMON} {VOCAB[10]}"~5) AND NOT {RARE}'), ["title"]),
        )
        await timeit("prefix query (zzmed*) in big", lambda: search(conn, fs["big"], q("big", "zzmed*"), ["title"]))

        print("\n--- project filter: inside the BM25 index (json) vs as SQL condition")
        small_pk = pks["small_0"]
        cs = compile_search(fs["small_0"], q("small_0", COMMON))
        query_only = cs.json_query["boolean"]["must"][1]

        async def sql_filter():
            cur = await conn.execute(
                "SELECT doc_id FROM documents WHERE id @@@ %s::jsonb AND project_pk = %s "
                "ORDER BY paradedb.score(id) DESC LIMIT 10",
                [Jsonb(query_only), small_pk],
            )
            return await cur.fetchall()

        async def json_filter():
            cur = await conn.execute(
                "SELECT doc_id FROM documents WHERE id @@@ %s::jsonb ORDER BY paradedb.score(id) DESC LIMIT 10",
                [Jsonb(cs.json_query)],
            )
            return await cur.fetchall()

        await timeit("common term in small project, project filter in index", json_filter)
        await timeit("common term in small project, project filter in SQL", sql_filter)

        print("\n--- filters and sorting")
        f = {"date": FilterSpec(gte="2010-01-01", lt="2011-01-01"), "source": FilterSpec(values=["source_1", "source_2"])}
        res = await timeit(
            "date range + keyword filter in big (no query)", lambda: search(conn, fs["big"], q("big", None, f), ["title"])
        )
        results["date range + keyword filter in big (no query)"]["hits"] = res.total
        await timeit(
            "medium query + date range filter in big",
            lambda: search(conn, fs["big"], q("big", MEDIUM, {"date": FilterSpec(gte="2010-01-01")}), ["title"]),
        )
        await timeit(
            "monthnr filter in big",
            lambda: search(conn, fs["big"], q("big", None, {"date": FilterSpec(monthnr=3)}), ["title"]),
        )
        await timeit(
            "sort by date desc, no query, big",
            lambda: search(conn, fs["big"], q("big"), ["title", "date"], sort=[("date", "desc")]),
        )
        await timeit(
            "sort by date desc, common query, big",
            lambda: search(conn, fs["big"], q("big", COMMON), ["title", "date"], sort=[("date", "desc")]),
        )
        await timeit(
            "page 1000 (offset 10000), common query by score, big",
            lambda: search(conn, fs["big"], q("big", COMMON), ["title"], page=1000, with_total=False),
        )

        print("\n--- snippets")
        snip = {"text": SnippetParams(nomatch_chars=100, max_matches=3, match_chars=50)}
        await timeit(
            "medium query in big, 10 results with snippets",
            lambda: search(conn, fs["big"], q("big", MEDIUM), ["title"], snippets=snip),
        )
        await timeit(
            "medium query in big, 100 results with snippets",
            lambda: search(conn, fs["big"], q("big", MEDIUM), ["title"], snippets=snip, per_page=100),
        )
        await timeit(
            "medium query in big, 100 results with full text",
            lambda: search(conn, fs["big"], q("big", MEDIUM), ["title", "text"], per_page=100),
        )

        print("\n--- aggregation (SQL GROUP BY)")
        await timeit("terms(source), all docs in big", lambda: aggregate(conn, fs["big"], q("big"), [Axis("source")]))
        await timeit(
            "month histogram, medium query in big",
            lambda: aggregate(conn, fs["big"], q("big", MEDIUM), [Axis("date", "month")]),
        )
        await timeit("month histogram, all docs in big", lambda: aggregate(conn, fs["big"], q("big"), [Axis("date", "month")]))
        await timeit(
            "quarter histogram (SQL date_trunc), all docs in big",
            lambda: aggregate(conn, fs["big"], q("big"), [Axis("date", "quarter")]),
        )
        await timeit(
            "year x source, common query in big",
            lambda: aggregate(conn, fs["big"], q("big", COMMON), [Axis("date", "year"), Axis("source")]),
        )
        await timeit("tags terms, all docs in big", lambda: aggregate(conn, fs["big"], q("big"), [Axis("tags")]))
        await timeit(
            "terms(source), all docs in medium_0", lambda: aggregate(conn, fs["medium_0"], q("medium_0"), [Axis("source")])
        )

        source_path = fs["big"].resolve("source")[0].path
        cb = compile_search(fs["big"], q("big"))

        async def pdb_agg():
            cur = await conn.execute(
                "SELECT pdb.agg(%s::jsonb) AS agg FROM documents WHERE id @@@ %s::jsonb",
                [Jsonb({"terms": {"field": source_path, "size": 100}}), Jsonb(cb.json_query)],
            )
            return await cur.fetchone()

        await timeit("terms(source), all docs in big, via pdb.agg (columnar)", pdb_agg)

        print("\n--- writes")
        big_fields = fs["big"].project_fields[pks["big"]]
        t0 = time.perf_counter()
        n = await update_tag_by_query(conn, fs["big"], q("big", MEDIUM), big_fields["tags"], "benchmark", "add")
        results["add tag to medium query in big"] = {"documents": n, "seconds": round(time.perf_counter() - t0, 2)}
        print(f"add tag to {n} documents: {time.perf_counter() - t0:.2f}s")

        copy_pk = await create_project(conn, "copy")
        copy_fields = await create_fields(conn, copy_pk, FIELD_TYPES)
        field_map = {big_fields[name]: copy_fields[name] for name in FIELD_TYPES}
        cm = compile_search(fs["big"], q("big", MEDIUM))
        t0 = time.perf_counter()
        n = await copy_documents(conn, pks["big"], copy_pk, field_map, "id @@@ %s::jsonb", [Jsonb(cm.json_query)])
        results["copy subset (medium query) of big"] = {"documents": n, "seconds": round(time.perf_counter() - t0, 2)}
        print(f"copy {n} documents to new project: {time.perf_counter() - t0:.2f}s")

        rng = random.Random(99)
        small_fields = fs["small_0"].project_fields[small_pk]
        await timeit(
            "upload batch of 100 docs into small project",
            lambda: upload_documents(conn, small_pk, [make_doc(rng) for _ in range(100)], small_fields),
        )

        print("\n--- table-per-project comparison: 200 empty tables with a bm25 index")
        t0 = time.perf_counter()
        for i in range(200):
            await conn.execute(f"CREATE TABLE bench_t{i} (id bigint primary key, text_data jsonb, meta_data jsonb)")  # type: ignore[arg-type]
            await conn.execute(
                f"CREATE INDEX bench_t{i}_bm25 ON bench_t{i} USING bm25 "  # type: ignore[arg-type]
                "(id, (text_data::pdb.unicode_words), (meta_data::pdb.literal))"
            )
        elapsed = time.perf_counter() - t0
        cur = await conn.execute(
            "SELECT sum(pg_total_relation_size(oid)) AS bytes FROM pg_class WHERE relname LIKE 'bench_t%%' AND relkind = 'r'"
        )
        row = await cur.fetchone()
        assert row is not None
        results["200 empty tables with bm25 index"] = {"seconds": round(elapsed, 1), "bytes_total": int(row["bytes"])}
        print(f"created in {elapsed:.1f}s, {int(row['bytes']) / 200 / 1024:.0f} KB per empty table incl. indexes")
        for i in range(200):
            await conn.execute(f"DROP TABLE bench_t{i}")  # type: ignore[arg-type]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--skip-load", action="store_true", help="Reuse previously loaded data")
    parser.add_argument("--output", default="prototype/benchmark_results.json")
    args = parser.parse_args()
    if args.skip_load:
        async with await AsyncConnection.connect(args.url, row_factory=dict_row) as conn:
            cur = await conn.execute("SELECT id, pk FROM projects")
            pks = {r["id"]: r["pk"] for r in await cur.fetchall()}
            await conn.execute("DELETE FROM projects WHERE id = 'copy'")
            await conn.commit()
    else:
        pks = await load(args.url, args.scale)
    await benchmark(args.url, pks)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, default=str)


if __name__ == "__main__":
    asyncio.run(main())
