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
documents(id, project_pk, doc_id, text_data jsonb, meta_data jsonb, extra_data jsonb, source jsonb,
          dedup_hash, sort_date, sort_number, sort_keyword, created_at, updated_at)
    PRIMARY KEY (id, project_pk), UNIQUE (project_pk, doc_id), UNIQUE (project_pk, dedup_hash)
    PARTITION BY HASH (project_pk): 64 partitions, each with its own BM25 index
    BM25 index on (id, project_pk, sort_date, sort_number, sort_keyword, text_data, meta_data)
document_vectors(document_id, project_pk, field_pk, embedding vector)   -- HNSW index per field
jobs(id, type, status, project_pk, params, progress, result, ...)  -- background jobs (e.g. copy)
roles, api_keys, requests, server_settings, object_storage   -- system data, plain tables
```

- **One table for all projects.** A project owns its documents. Cross-project queries filter on several projects.
  (An empty table with a BM25 index costs ~2.8 MB, so a table per project would be expensive.)
- **Partitioned by project.** The documents table is hash partitioned on `project_pk` into 64 partitions, each with
  its own BM25 index. A query on a project only uses its own partition (the search adds a SQL condition on
  `project_pk` for this), and after a mass update only that partition's index needs to be rebuilt
  (`amcat4 optimize --reindex --project <id>`). Rebuilding runs online: reads and writes continue. The cost is
  ~180 MB for the 64 empty indexes, and the number of partitions can only be changed by rewriting the table.
- **Values are keyed by field key (`f<field pk>`), not by name.** Renaming a field (`systemdata.fields.rename_field`)
  only changes the field definition. The same name can have different keys in different projects; queries over
  multiple projects resolve a name to one key per project.
- **Storage columns by how a field is indexed:** `text_data` (tokenized, with positions: text fields), `meta_data`
  (exact and columnar: keyword, tag, url, number, integer, boolean, date, geo_point, multimedia), `extra_data` (stored
  only: object), `document_vectors` (vector). A new field is a new json key, so the BM25 index never needs to be
  rebuilt for new fields.
- **Sort slots.** pg_search cannot sort on json keys inside the index. Each project can put one date, one number and
  one keyword field in a *sort slot*: a real column (`sort_date`, `sort_number`, `sort_keyword`) in the index. Sorting
  on such a field is fast; sorting on other fields works but reads all matching rows. The first date field gets the
  date slot automatically; others are set with `fast_sort` in the field update API.
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
  `source`.
  Read-only *reference* projects are a planned feature (see the TODO in `postgres/layout.py`).
- **Backups:** standard postgres tools (`pg_dump`, or pgBackRest for point in time recovery) replace elastic snapshots.

## What we learned about pg_search

| Finding | Consequence |
|---|---|
| Structured json queries on json paths support match, phrase (with slop), phrase_prefix, fuzzy, boolean, term, range (numbers, dates, strings), exists (columnar fields) | Our query parser compiles to these |
| The string query parser (`paradedb.parse`) on json paths does not support wildcards, phrase slop or date ranges, and `AND NOT` silently returns nothing | We use our own parser |
| A query without a field does not search all keys of a json column | We search the (queryable) text fields explicitly |
| Regex queries do not work on json paths | Only trailing wildcards (`immigr*`) are supported |
| Dates stored as RFC3339 strings are typed as dates (range queries, columnar) | No numeric date representation needed |
| No Top-K sorting on json keys | Sort slots |
| Expressions (`date_trunc`, casts) are not pushed into the index; grouping on a raw json keyword is | Derived date keys; keyword grouping inside the index |
| When grouping inside the index, json dates/numbers are returned in an internal representation | Dates/numbers without interval are grouped in SQL |
| `snippet_positions` returns utf-8 byte offsets, and no positions for prefix queries | Converted to characters, combined with our own matcher |
| Small inserts are buffered in a *mutable segment*, which made every query 5-10x slower after many small uploads | The index is created with `mutable_segment_rows = 0` |
| Updating many rows (e.g. tagging a large set, putting a field in a sort slot) leaves the BM25 index bloated and slower, also after `VACUUM` | Rebuild the index online with `amcat4 optimize --reindex [--project <id>]` (`REINDEX INDEX CONCURRENTLY`) after large updates; with partitioning only the partition of the project |
| BM25 indexes work on partitioned tables: one index per partition, partition pruning and Top-K sorting work | The documents table is partitioned on project |
| `pdb.agg` terms counts on arrays are approximate; date histograms only support fixed intervals | Exact SQL aggregation |
| The paradedb image also contains pgvector and PostGIS | Vectors use pgvector |

## Benchmark

The numbers below were measured before the documents table was partitioned.

`uv run python benchmark/pg_benchmark.py --scale 1.0` (results in `benchmark/benchmark_results.json`)

- **Data:** 1,000,000 synthetic documents (title + ~150 word text, keyword, date, integer, tags) in 821 projects: one big
  project (500k), 20 medium (15k each), 800 small (250 each). Zipf-distributed vocabulary; a *rare* term (0.05% of
  documents), a *medium* term (2%) and a *common* term (~99%).
- **Machine:** 4-core container, 15 GB RAM, untuned postgres settings in the paradedb image.
- Times are medians of 5 runs after a warm-up, via the same functions the API uses (so including field lookups,
  result conversion and the count for the total number of results).

Fresh data (loaded with the normal upload code, then `VACUUM`):

| Operation | Time |
|---|---|
| Load 1M docs (4 parallel uploads of 5000 documents, incl. generating them) | 181 s (5.5k docs/s) |
| Storage: table incl. TOAST / BM25 index / total | 1954 MB / 467 MB / 2.5 GB |
| Search rare / medium / common term in big project (500k), 10 results + total count | 46 / 42 / 64 ms |
| Search in a medium (15k) / small (250) project | 30-37 / 34-41 ms |
| Search common term across 20 medium projects | 94 ms |
| Complex boolean query (OR, phrase with slop, NOT) in big | 167 ms |
| Prefix query in big | 46 ms |
| Date range + keyword filter / month number filter in big | 46 / 32 ms |
| Sort by date (sort slot), without / with common query, big | 45 / 74 ms |
| Sort by a number *without* sort slot, big (reads all 500k rows) | 4.1 s |
| 100 results with snippets | 53 ms |
| Month histogram for a query (10k hits) in big | 40 ms |

After putting a number field of the big project in a sort slot (which updates all 500k rows, 102 s) and rebuilding
the index (`VACUUM` + `REINDEX INDEX CONCURRENTLY`, 110 s):

| Operation | Time |
|---|---|
| Sort by that number (sort slot), big | 248 ms |
| Page 1000 (offset 10,000), common query, big | 292 ms |
| Aggregate terms(source) / month histogram over all 500k docs of big | 253 / 256 ms |
| Year x source for the common query (500k hits) | 283 ms |
| Tag terms over all docs of big (SQL, not inside the index) | 716 ms |
| Add a tag to 9.8k documents (by query) | 2.2 s |
| Copy 9.8k documents (subset by query) to a new project | 2-3 s |
| Upload 100 documents into a small project | 50-60 ms |

Earlier runs on a freshly built index showed aggregations over the whole big project in 17-40 ms, so mass updates
of a large project leave a measurable cost even after vacuum and reindex (probably the bloated table: a full
`VACUUM FULL` was not tested).

## Open issues

- **Mass updates** (updating all documents of a large project) are slow (~100 s for 500k documents, every update
  rewrites the row and its index entry) and degrade query performance until `amcat4 optimize --reindex`; aggregations
  stayed ~5x slower than on fresh data. Worth investigating (autovacuum settings, `VACUUM FULL`, newer pg_search).
- Once, an update by query directly after `REINDEX INDEX CONCURRENTLY` (with autovacuum running) took more than 10
  minutes before it was cancelled; it took 2 s when repeated. Not reproduced; keep an eye on this.
- Tag aggregations are done in SQL (unnest), which is the slowest aggregation (0.7 s for 500k documents).
- Geo distance queries would need PostGIS.
- Read-only reference projects (see design discussion) are not implemented.
- Postgres settings are untuned; real (longer, natural language) texts and larger corpora should be tested.
