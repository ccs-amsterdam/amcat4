# PostgreSQL storage: design, findings and benchmark

AmCAT stores all data in PostgreSQL, using the [pg_search](https://github.com/paradedb/paradedb) extension for
BM25 full-text search and [pgvector](https://github.com/pgvector/pgvector) for vectors. The
[`paradedb/paradedb`](https://hub.docker.com/r/paradedb/paradedb) image contains both. Developed and tested with
PostgreSQL 18.6 and pg_search 0.26.0.

The database code is in `amcat4/postgres/` (with the design in `layout.py`); the business logic in `amcat4/projects/`
and `amcat4/systemdata/` uses it. The tables are defined by the (alembic) migrations in `amcat4/migrations/versions/`,
which are run at startup.
The benchmark script is `benchmark/pg_benchmark.py`.

## Design

```
projects(pk, id, name, description, folder, contact, image, archived)
fields(pk, project_pk, name, type, unique_field, metareader, reader, client_settings, sort_slot)
documents(id, partition_id, project_pk, doc_id, text_fields jsonb, exact_fields jsonb, stored_fields jsonb,
          copied_from jsonb, dedup_hash, date, source, created_at, updated_at)
    PRIMARY KEY (id, partition_id), UNIQUE (partition_id, project_pk, doc_id), UNIQUE (.., dedup_hash)
    PARTITION BY LIST (partition_id): partitions are created when needed, each with its own BM25 index
    BM25 index on (id, project_pk, date, source, text_fields, exact_fields)
document_vectors(document_id, partition_id, field_pk, embedding vector)   -- HNSW index per field
jobs(id, type, status, project_pk, params, progress, result, ...)  -- background jobs (e.g. copy)
roles, api_keys, requests, server_settings, object_storage   -- system data, plain tables
```

- **One table for all projects.** A project owns its documents. Cross-project queries filter on several projects.
  (An empty table with a BM25 index costs ~2.8 MB, so a table per project would be expensive.)
- **Partitioned by project.** The documents table is list partitioned on `partition_id`, each partition with its own
  BM25 index. Every project is assigned to a partition when it is created: the newest one, until its BM25 index
  reaches `partition_max_gb`, after which a new partition is created. A query on a project only uses its own
  partition (queries add a SQL condition on `partition_id` for this), and after a mass update only that partition's
  index needs to be rebuilt (`amcat4 optimize --reindex --project <id>`). Rebuilding runs online: reads and writes
  continue.
- **Values are keyed by field key (`f<field pk>`), not by name.** Renaming a field (`systemdata.fields.rename_field`)
  only changes the field definition. The same name can have different keys in different projects; queries over
  multiple projects resolve a name to one key per project.
- **Storage columns by how a field is indexed:** `text_fields` (tokenized, with positions: text fields), `exact_fields`
  (exact and columnar: keyword, tag, url, number, integer, boolean, date, geo_point, multimedia), `stored_fields` (stored
  only: object), `document_vectors` (vector). A new field is a new json key, so the BM25 index never needs to be
  rebuilt for new fields.
- **Standard columns.** pg_search cannot sort on json keys inside the index. Each project can map one date field and
  one keyword field to the standard `date` and `source` columns, which are real columns in the index. Sorting on
  such a field is fast; sorting on other fields works but reads all matching rows. The first date field and a keyword
  field called `source` are mapped automatically; others are set with `fast_sort` in the field update API.
- **Derived date keys.** For date fields, `f12_year`, `f12_month`, `f12_week`, `f12_day`, `f12_monthnr`,
  `f12_dayofweek`, ... are stored as well, so date histograms and date part filters run inside the index.
- **Geo points** are stored as `{"lat": .., "lon": ..}`, so `location.lat` and `location.lon` can be used in range
  filters and queries (bounding boxes).
- **Vectors** are stored in `document_vectors`, with a pgvector HNSW index (cosine) per field, created on first upload
  (which fixes the number of dimensions). Queries can order results by similarity to a vector (`similar`).
- **Unique fields.** If a project has unique fields, a hash of their values is stored in `dedup_hash` (unique per
  project), so uploading the same document twice updates it (or fails, for `create`) instead of creating a duplicate.
  Document ids are independent of these values.
- **Query parsing.** Query strings are parsed by AmCAT (`postgres/querystring.py`) and compiled to pg_search's
  structured json queries. This translates field names to keys, determines which fields are searched by default, and
  is the place where field-level access (which fields may be queried) can be enforced.
- **Snippets and highlighting** are built by AmCAT from the stored text, so the limits for metareaders are enforced in
  our own code. Match positions come from the parsed query, combined with `paradedb.snippet_positions`.
- **Pagination** uses stateless cursors (keyset on the internal id for unsorted results, otherwise offsets).
- **Copies** (a `copy` job) physically copy (a subset of) documents and fields in batches, recording provenance in
  `copied_from`.
  Read-only *reference* projects are a planned feature (see the TODO in `postgres/layout.py`).
- **Backups:** standard postgres tools (`pg_dump`, or pgBackRest for point in time recovery) replace elastic snapshots.

## What we learned about pg_search

| Finding | Consequence |
|---|---|
| Structured json queries on json paths support match, phrase (with slop), phrase_prefix, fuzzy, boolean, term, range (numbers, dates, strings), exists (columnar fields) | Our query parser compiles to these |
| The string query parser (`paradedb.parse`) on json paths does not support wildcards, phrase slop or date ranges, and `AND NOT` silently returns nothing | We use our own parser |
| A query without a field does not search all keys of a json column | We search the (queryable) text fields explicitly |
| Regex queries do not work on json paths (the pattern is matched against the whole stored term, ignoring the field path) | Only trailing wildcards (`immigr*`) are supported |
| Dates stored as RFC3339 strings are typed as dates (range queries, columnar) | No numeric date representation needed |
| No Top-K sorting on json keys | Standard `date` and `source` columns |
| Expressions (`date_trunc`, casts) are not pushed into the index; grouping on a raw json keyword can be (but in the benchmark queries it is not, see open issues) | Derived date keys |
| When grouping inside the index, json dates/numbers are returned in an internal representation | Dates/numbers without interval are grouped in SQL |
| `snippet_positions` returns utf-8 byte offsets, and no positions for prefix queries | Converted to characters, combined with our own matcher |
| Small inserts are buffered in a *mutable segment*, which made every query 5-10x slower after many small uploads | The index is created with `mutable_segment_rows = 0` |
| Updating many rows (e.g. tagging a large set, mapping a field to a standard column) leaves the BM25 index bloated and slower, also after `VACUUM` | Rebuild the index online with `amcat4 optimize --reindex [--project <id>]` (`REINDEX INDEX CONCURRENTLY`) after large updates; with partitioning only the partition of the project. In the benchmark this did not fully restore the speed of aggregations over a whole project (see below) |
| BM25 indexes work on partitioned tables: one index per partition, partition pruning and Top-K sorting work | The documents table is partitioned on project |
| SQL conditions on columns that are not in the BM25 index are checked against the table for every match (2-10x slower for queries with many matches) | `partition_id` is in the index |
| `pdb.agg` terms counts on arrays are approximate; date histograms only support fixed intervals | Exact SQL aggregation |
| The paradedb image also contains pgvector and PostGIS | Vectors use pgvector |

## Benchmark

`uv run python benchmark/pg_benchmark.py --scale 1.0` (results in `benchmark/benchmark_results.json`)

- **Data:** 1,000,000 synthetic documents (title + ~150 word text, keyword, date, integer, tags) in 821 projects: one big
  project (500k), 20 medium (15k each), 800 small (250 each). Zipf-distributed vocabulary; a *rare* term (0.05% of
  documents), a *medium* term (2%) and a *common* term (~99%). All projects fit in one partition (the BM25 index is
  ~500 MB), so the big project shares its partition and index with all other projects.
- **Machine:** desktop (i9-14900KF, 32 threads, 62 GB RAM), postgres in the paradedb docker image without resource
  limits and with untuned settings.
- Times are medians of 5 runs after a warm-up, via the same functions the API uses (so including field lookups,
  result conversion and the count for the total number of results).
- The read operations are measured in four phases: **after upload** (loaded with the normal upload code, then
  `VACUUM`: what users get by default); **after upload + reindex** (`REINDEX INDEX CONCURRENTLY`, as
  `amcat4 optimize --reindex` does); **after a mass update** of the big project (all 500k documents rewritten twice,
  by unmapping and remapping the `source` column, then `VACUUM`); and **after mass update + reindex**.
- Parallel query is turned off in the benchmark (`max_parallel_workers_per_gather = 0`), so every query runs in a
  single process. pg_search estimates the number of matches from the largest index segment only
  ([paradedb#6563](https://github.com/paradedb/paradedb/issues/6563)), and postgres decides on parallel workers
  based on that estimate. With parallel query on, whether a query got extra workers depended on the index layout:
  aggregations over the whole big project took ~100 ms with 4 processes, or ~200 ms with 1, in otherwise identical
  situations. With parallel query on, operations over (almost) all documents of a big project can be up to ~2x
  faster than below.

| Operation | After upload | + reindex | After mass update | + reindex |
|---|---|---|---|---|
| Search rare / medium term in big project (500k), 10 results + total count | 29 / 29 ms | 15 / 12 ms | 13 / 15 ms | 12 / 11 ms |
| Search common term in big (~495k hits, so mostly counting) | 128 ms | 111 ms | 123 ms | 111 ms |
| Search in a medium (15k) / small (250) project | 13-21 ms | 6-9 ms | 6-9 ms | 5-9 ms |
| Search common term across 20 medium projects | 134 ms | 100 ms | 100 ms | 102 ms |
| Complex boolean query (OR, phrase with slop, NOT) in big | 125 ms | 88 ms | 108 ms | 87 ms |
| Prefix query in big | 30 ms | 11 ms | 13 ms | 11 ms |
| Date range + keyword filter / month number filter in big | 25 / 25 ms | 11 / 19 ms | 12 / 16 ms | 11 / 18 ms |
| Sort by date (date column), without / with common query, big | 104 / 133 ms | 106 / 116 ms | 97 / 128 ms | 101 / 116 ms |
| Sort by source (source column), big | 103 ms | 102 ms | 98 ms | 99 ms |
| Page 1000 (offset 10,000), common query, big | 147 ms | 134 ms | 136 ms | 133 ms |
| 100 results with snippets, big | 35 ms | 18 ms | 17 ms | 19 ms |
| Month histogram for a query (10k hits) in big | 26 ms | 15 ms | 15 ms | 15 ms |
| Terms(source) / month histogram over all 500k docs of big | 214 / 215 ms | 200 / 199 ms | 202 / 210 ms | 199 / 205 ms |
| Year x source for the common query (495k hits) | 267 ms | 237 ms | 254 ms | 252 ms |
| Tag terms over all docs of big (SQL, not inside the index) | 356 ms | 348 ms | 351 ms | 346 ms |
| BM25 index: segments / size | 240 / 503 MB | 31 / 621 MB | 39 / 970 MB | 32 / 591 MB |
| Table incl. TOAST | 1954 MB | 1954 MB | 3907 MB | 3907 MB |

Other operations:

| Operation | Time |
|---|---|
| Load 1M docs (4 parallel uploads of 5000 documents, incl. generating them) | 62 s (16k docs/s) |
| `REINDEX INDEX CONCURRENTLY` of the whole index (1M docs) | 7 s |
| Update all 500k documents of big (unmapping or mapping the source column) | 24-26 s |
| `VACUUM` after that | 28 s |
| Sort by source *without* the source column, big (reads all 500k rows) | 1.7 s |
| Add a tag to 9.8k documents (by query) | 0.7 s |
| Copy 9.8k documents (subset by query) to a new project | 0.9 s |
| Upload 100 documents into a small project | 23 ms |

**What this means:**
- Most searches and filters take 5-30 ms. Operations that touch (almost) all 500k documents of a project (counting
  a common term, sorting everything, aggregating the whole project) take ~100-250 ms in a single process; tag
  aggregations (done in SQL) ~350 ms.
- **Reindexing after uploads matters most.** Every upload batch becomes its own index *segment*, and pg_search does
  not merge them (`VACUUM` doesn't either): after uploading there were 240 segments of at most 5000 documents, and
  searches have to visit all of them. A reindex builds ~30 large segments, which makes most searches 2-3x faster
  (e.g. 21 -> 6 ms in a small project). It is cheap (7 s for 1M documents, online) but makes the index ~20% larger.
- **A mass update does not make searches much slower** (the updated documents are added as a few large segments),
  but the index nearly doubles (503 -> 970 MB) until it is reindexed, and some queries get a bit slower (complex
  boolean query 1.2x). Reindexing fixes that.
- The table doubles in size after rewriting all documents of the big project; `VACUUM` makes that space reusable
  but does not give it back (`VACUUM FULL` does, but locks the table).
- Aggregations are not done inside the index: the values are read from the table and grouped by postgres (see open
  issues), which is why they don't benefit from a reindex.

## Open issues

- **Mass updates** (updating all documents of a large project) take ~25 s for 500k documents (every update rewrites
  the row and its index entry), and should be followed by a reindex.
- **Parallel query depends on the index layout,** because pg_search estimates the number of matches from the
  largest segment ([paradedb#6563](https://github.com/paradedb/paradedb/issues/6563)). So the same aggregation can
  take ~100 or ~200 ms depending on how the index happens to be built. Known upstream bug; we don't work around it.
- **Uploads leave many small index segments** (one per upload batch), which makes searches 2-3x slower until the
  index is rebuilt. Options: tune pg_search's segment merging, or reindex a partition after large uploads (e.g. in a
  background job).
- Grouping on json keys (terms, derived date parts) was meant to run inside the index, but in the benchmark Postgres
  reads the values from the table and groups them itself. Worth checking which aggregations pg_search can push down.
- Once, an update by query directly after `REINDEX INDEX CONCURRENTLY` (with autovacuum running) took more than 10
  minutes before it was cancelled; it took 2 s when repeated. Not reproduced; keep an eye on this.
- Tag aggregations are done in SQL (unnest), not inside the index (~350 ms for 500k documents in the benchmark).
- Geo distance queries would need PostGIS.
- Read-only reference projects (see design discussion) are not implemented.
- Postgres settings are untuned; real (longer, natural language) texts and larger corpora should be tested.
