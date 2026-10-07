# PostgreSQL (pg_search) backend prototype

This directory documents the prototype for replacing Elasticsearch with PostgreSQL + [pg_search](https://github.com/paradedb/paradedb)
(ParadeDB's BM25 extension). The reusable code lives in `amcat4/postgres/`, the tests in `tests_postgres/`, and the benchmark
in `prototype/pg_benchmark.py`.

Tested with the `paradedb/paradedb:latest` image: **PostgreSQL 18.6, pg_search 0.26.0** (also ships pgvector and PostGIS).

## Design

```
projects(pk, id, name, ...)
fields(pk, project_pk, name, type, unique_field, metareader, client_settings)      -- name is a label, pk is the identity
documents(id bigint PK, project_pk, doc_id, dedup_hash, text_data jsonb, meta_data jsonb, extra_data jsonb, source jsonb)
    UNIQUE (project_pk, doc_id)
    UNIQUE (project_pk, dedup_hash) WHERE dedup_hash IS NOT NULL
    BM25 index on (id, project_pk, text_data::pdb.unicode_words, meta_data::pdb.literal)
```

- **One table for all projects.** A project owns its documents (`project_pk`). Cross-project queries are a filter on several
  project pks.
- **Values are keyed by field key (`f<field pk>`), not by name.** Renaming a field is a metadata update. The same name can have
  different types in different projects; a multi-project query resolves a name to one key per project (`FieldSet`).
- **Columns by indexing behaviour:** `text_data` (tokenized, positions; text fields), `meta_data` (exact + columnar/fast;
  keyword, tag, url, number, integer, boolean, date, multimedia paths), `extra_data` (stored only; object, vector, geo_point).
  Adding a field adds a json key, so the BM25 index **never needs to be rebuilt** for new fields.
- **Our own query parser** (`querystring.py`) compiles Lucene-like query strings to pg_search's structured json queries.
  This maps names to keys, enforces which fields may be queried (field-level access), and decides the default search fields.
- **Snippets are built by AmCAT** (`snippets.py`) from the stored text and the match positions reported by
  `paradedb.snippet_positions`, so the limits for metareaders are enforced in our own code.
- **Identity vs deduplication are separate:** `doc_id` is given or a random uuid and never changes; optional *unique fields*
  are hashed into `dedup_hash`, enforced by a unique index, and uploads choose update / replace / skip on conflict.
- **Copies are physical** (`copy_documents`, optionally a subset by query and a subset of fields), recording provenance in
  `source`. *Referencing* documents of other projects (read-only reference projects) is a later feature, see the TODO in
  `schema.py`.

## What we learned about pg_search

### Works (on jsonb paths)
| Feature | How |
|---|---|
| Full-text match on a json key | `{"match": {"field": "text_data.f12", "value": "..."}}` (tokenizes the value) |
| Phrase, phrase with slop | `{"phrase": {"field": ..., "phrases": [...], "slop": n}}` |
| Prefix (`immigr*`) | `{"phrase_prefix": {"field": ..., "phrases": ["immigr"]}}` |
| Fuzzy | `{"fuzzy_term": {"field": ..., "value": ..., "distance": n}}` |
| Boolean must / should / must_not, boost | `{"boolean": {...}}`, `{"boost": {...}}` |
| Keyword / tag (array) exact match | `{"term": {"field": "meta_data.f3", "value": "news"}}` |
| Numeric ranges (gt, gte, lt, lte) | `{"range": {"field": ..., "lower_bound": {"excluded": 5}, "upper_bound": null}}` |
| **Date ranges** | same `range` query; dates stored as RFC3339 strings are typed as dates by Tantivy. Numeric date representation is not needed. |
| Exists on meta fields | `{"exists": {"field": "meta_data.f6"}}` |
| Project filter inside the index | `{"term": {"field": "project_pk", "value": 3}}` |
| Match positions for snippets | `paradedb.snippet_positions(text_data->'f12')` (**utf-8 byte offsets**, converted in `snippets.py`) |
| BM25 score | `paradedb.score(id)` |
| Columnar aggregation | `pdb.agg('{"terms": {"field": "meta_data.f3"}}')` |

### Does not work / caveats
| Issue | Consequence / workaround |
|---|---|
| A query without a field does not search all keys of a json column | We expand to the queryable text fields ourselves (we want that anyway for access control) |
| `paradedb.parse` (string syntax) on json paths: no wildcards, no phrase slop, no date ranges, `AND NOT` silently returns nothing | We use our own parser and the structured json queries, which do support all of this |
| Regex queries return nothing on json paths | Only trailing wildcards are supported (`immigr*`); `wom?n` / `*grant` give an error |
| `exists` on text (non-columnar) json fields is not supported | Checked in SQL: `text_data ? 'f12'` |
| `pdb.agg` date histograms only support `fixed_interval`, not calendar intervals | Aggregations use plain SQL `GROUP BY date_trunc(...)` |
| Only one BM25 index per table, and its column list is fixed | Fine with the jsonb design; new fields are new keys |
| `key_field` is deprecated (no-op) since 0.26 | Not used |
| An empty table with a BM25 index takes ~2.8 MB | Confirms the single-table design over a table per project |
| Tokenizer is per json column, not per key | One tokenizer for all text fields (no per-project stemming/language yet) |
| **No Top-K sort on json keys** (in any form: cast, `COLLATE "C"`, `top_hits`): sorting 500k docs by a json date took 1-2 s | The primary date field of a project is also stored in a real `sort_date` column in the index: 20 ms |
| **Expressions like `date_trunc` / `extract` are not pushed into the index**: date histograms and month filters scanned the heap (0.7-1.4 s for 500k docs) | Date fields get *derived keys* at write time (`f12_year`, `f12_month`, `f12_week`, `f12_day`, `f12_monthnr`, `f12_dayofweek`, ...); grouping on a plain json key *is* pushed down: 20-75 ms |
| Many small writes leave many index segments, which slows every query 3-5x (80-120 ms instead of 15-35 ms) | `VACUUM` merges segments (`force_merge` is deprecated). Run it after bulk uploads; autovacuum and the background merger also do it eventually |
| `pdb.agg` terms counts on arrays (tags) are approximate | Exact SQL (`jsonb_array_elements_text`) for now: 460 ms for 500k docs, the slowest remaining aggregation |

## Benchmark

`prototype/pg_benchmark.py`, results in `prototype/benchmark_results.json`.

- **Data:** 1,000,000 synthetic documents (title + ~150 word text, keyword, date, integer, tags) in 821 projects: one big
  project (500k), 20 medium (15k each), 800 small (250 each). Zipf-distributed vocabulary; a *rare* term (0.05% of
  documents), a *medium* term (2%) and a *common* term (~99%).
- **Machine:** 4-core container, 15 GB RAM, default (untuned) postgres settings in the paradedb image.
- Times are medians of 5 runs after a warm-up, from Python (psycopg) including result conversion.
  "search" includes a separate count query for the total.

| Operation | Time |
|---|---|
| Load 1M docs (4 writers, incl. generating them) | 114 s (8.8k docs/s) |
| Rebuild the whole BM25 index (1M docs) | ~60 s |
| Storage: table incl. TOAST / BM25 index / total | 1954 MB / 479 MB / 2.5 GB |
| Search rare / medium / common term in big project (500k) | 28 / 24 / 36 ms |
| Search in medium (15k) / small (250) project | 15-17 / 23-26 ms |
| Search common term across 21 projects | 100 ms |
| Count only, common term in big | 17 ms |
| Complex boolean query (OR, phrase with slop, NOT) in big | 123 ms |
| Prefix query in big | 26 ms |
| Date range + keyword filter in big | 23 ms |
| Month number filter in big | 18 ms |
| Sort by date (no query / common query) in big | 21 / 41 ms |
| Page 1000 (offset 10,000) | 58 ms |
| 100 results with snippets | 34 ms |
| Aggregate terms(source) / month histogram / year x source (common query), all of big | 38 / 37 / 74 ms |
| Aggregate by quarter (SQL date_trunc) / tags (SQL unnest), all of big | 323 / 461 ms |
| Add tag to 9.8k documents (by query) | 1.6 s |
| Copy 9.8k documents (subset by query) to a new project | 1.7 s |
| Upload 100 docs into a small project | 24 ms |
| An *empty* table with a BM25 index | 2.8 MB |

Project filtering inside the index vs. as SQL condition made no difference (6 ms both), so the planner handles both well.

## Answers to the prototype questions

1. **Search without a field over all json keys?** No. We expand to the queryable text fields ourselves, which we need for
   field-level access control anyway.
2. **Explicit default field list?** Yes, by generating a boolean OR over the fields (our parser does this).
3. **Dates in json?** Work natively when stored as RFC3339 strings (range queries, columnar aggregation). A numeric
   representation is not needed. Range filters (`gt`, `gte`, `lt`, `lte`) work for numbers, dates and keywords.
4. **Cost of idle projects?** In the single-table design: one row in `projects` and a few in `fields`. A table per project
   would cost 2.8 MB *per empty table* (2.8 GB for 1000 projects), so the single table is clearly better.
5. **Project filter inside the index?** Works and is fast; also when combined with queries, filters, sorting and aggregation.

## Open issues / next steps

- Aggregation axis names can collide with the count column `n` (same as the current elastic code).
- Scroll/cursor pagination (keyset on sort key + id) instead of offset for downloads.
- Field types `vector` (pgvector, included in the image) and `geo_point` (PostGIS) are only stored, not indexed.
- Possibly promote more fields to real columns (e.g. a numeric sort column) if sorting large projects on other fields
  turns out to be common.
- Tune postgres (shared_buffers etc.) and test with realistic (longer, real-language) texts and larger corpora.
- Port the system data (users, roles, api keys, settings, requests, object storage register) to plain tables.
- Wire this backend into the API, replacing `amcat4/projects/*` and `amcat4/systemdata/*`.

