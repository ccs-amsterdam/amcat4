# Postgres migration: elastic-era compromises and how they were resolved

The first version of the migration kept the existing API wherever possible. Since the new version is not in
production yet, most of those compromises have now been removed. This file lists what changed (useful for updating
clients such as the R/Python packages and scrapers) and what is still open.

## Resolved (breaking changes for clients)

| Topic | Before (elastic style) | Now |
|---|---|---|
| Identity / dedup | `identifier` fields; document id = hash of identifier values | `unique` fields: a separate dedup hash (unique per project) decides which documents are the same; document ids stay stable and unique values can be corrected |
| Field types | `elastic_type` fixed at creation, restricted type changes | Only the AmCAT type. Any type can be converted (`PUT /fields` with `type`); values are converted in batches and the change fails (and changes nothing) if a value cannot be converted |
| Renaming fields | not possible | `PUT /index/{ix}/fields` with `{field: {name: new_name}}` |
| Field visibility | metareader access only restricted returned values | `reader: {visible, queryable}` and `metareader: {access, max_snippet, queryable}`. `queryable` defaults to "same as visible"; fields can be visible but not queryable, or queryable but invisible (non-consumptive research). Writers and admins see everything |
| Uploads | `index` / `create` / `update` / `upsert`, result `{successes, failures}` | `create` / `update` / `upsert` / `replace` (default), all-or-nothing transaction, result `{created, updated}`, errors are 409 (conflicts) or 422 (invalid values) |
| Reindex | synchronous, pretended to be a task (in-memory) | `POST /index/{ix}/copy` creates a job; `GET /jobs`, `GET /jobs/{id}`, `DELETE /jobs/{id}` (cancel). Jobs run in a worker loop in the API process, in batches of 2000 documents, tracking the last copied id, so they continue after a restart. `/task/{id}` is removed |
| Refresh | no-op endpoint and parameter | removed |
| Scrolling | `scroll` / `scroll_id` with a server-side table | cursor pagination: the response meta has `next`; send the same query with `after=next`. Without sort/query the cursor is keyset on the internal id (fast for downloading everything), otherwise an offset |
| Aggregation pagination | `after` offsets | no pagination; `order` (`axes` or `count`) and `limit` (default 1000, max 10000), meta has `truncated` |
| Snippets | characters (`nomatch_chars`, `match_chars`), elastic highlighter behaviour | words: `words_per_match`, `max_matches`, `nomatch_words` (first N words if there are no matches); old parameters are rejected |
| Multiple projects | `/index/a,b,c/query` | `POST /query` and `POST /aggregate` with `projects: [...]` in the body; per-project endpoints take a single project |
| Field stats / values | elastic stats shape; values errored above 2000 | stats `{count, min, max, avg}` (dates as ISO); values are the most frequent values, `size` default 200, max 2000 |
| Query errors | generic | 400 with the query label, e.g. `Error in query 'q1' ('te*xt'): Wildcards are only supported at the end of a word ...`. OR stays the default operator |
| Project references | roles, requests and object storage used the project id string | foreign keys to `projects.pk` with `ON DELETE CASCADE` |
| Unused parameters | `list_fields(auto_repair)`, `rm_pending_migrations`, `migrate --no-rm-pending` | removed |

New features: vector similarity search (`similar: {field, vector}` in the query body, results ordered by
`_similarity`), and provenance of copied documents (`_copied_from: {project, doc_id}` on the single document endpoint).

## Importing exports from the current (elastic) servers

`POST /index/import` (and the chunked `/index/import/metadata` + `/index/{ix}/import/documents`) accept the existing
export format. Field definitions are converted by `amcat4.projects.legacy`: `elastic_type` is dropped, `identifier`
becomes `unique`, and snippet limits are converted from characters to words (6 characters per word). Document ids
from the export are kept.

## Kept on purpose

- `tag` stays a separate type: tags are keywords with their own UI and endpoints (`tags_update`).
- Guest roles are still stored as a role with email `*` (and domain roles as `*@domain`).
- Server settings and api key restrictions are merged on update (partial updates).
- The aggregation count column is still called `n` (collides with a field called `n`); metrics are `avg_field` etc.

## Still open

- Rename "index" to "project" in the API paths (TODO in `api/index.py`).
- Jobs are generic (`projects/jobs.py`, register a handler in `HANDLERS`), e.g. for preprocessing, but only `copy`
  exists. Old jobs are never cleaned up.
- Read-only reference projects (sharing documents without copying) are not implemented.
- Mass updates of large projects are slow and degrade query performance until a reindex (see `benchmark/README.md`).
