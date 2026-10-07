# Postgres migration: compromises to review

During the migration, the existing API and behaviour were kept wherever possible, so that clients (frontend,
R/Python packages, scrapers) keep working and the existing tests could be used as a specification. In a number of
places this means we copied elasticsearch behaviour that is no longer necessary, or not the most natural choice in
postgres. This file lists those places, roughly in order of how much I think they are worth revisiting.

## API and behaviour

### Scrolling (`scroll` / `scroll_id`)
**Now:** a server-side `scrolls` table stores the query; the same scroll id is returned on every call and the
server advances the position, and contexts expire after the given time (`"5m"`). This mimics elastic, whose scroll
contexts exist because elastic needs to keep a point-in-time snapshot of its segments.
**Better:** stateless cursor pagination. Return a (signed) `after` token containing the sort values and id of the last
result, and query `WHERE (sort, id) > (...)`. No server state, no expiry, works across server processes, and the same
mechanism can replace deep `page` offsets (which get slow: page 1000 took ~150-300 ms). The scroll parameters could
be kept as a deprecated alias.

### Document ids for projects with identifier fields
**Now:** like elastic, the document id is a hash of the identifier values.
**Better (as discussed):** decouple identity from deduplication. Keep a stable id, and enforce uniqueness of the
identifier fields with a unique (hash) column, with `ON CONFLICT` deciding between skip / update / error. This also
makes it possible to correct a value in an identifier field.

### `elastic_type` and the type change rules
**Now:** fields still have an `elastic_type` (e.g. `keyword`, `wildcard`, `double`, `long`), which is fixed at creation
and determines which AmCAT types a field can be changed to (via the old elastic type map). This was kept so the
frontend (field editing, upload type detection) works unchanged.
**Better:** the elastic types have no meaning anymore. Storage is only determined by the AmCAT type (text, exact
values, vector, stored-only object). Changing a type can simply rewrite the values of that field (one `UPDATE`), so
most type changes could be allowed, with validation of the existing values. The frontend could then drop the
elastic type concept.

### `tag` vs `keyword`
**Now:** tags are a separate type (lists of keywords), as in amcat-on-elastic.
**Better:** in postgres a keyword field could just allow multiple values. Worth considering whether the distinction is
still useful for users.

### Reindex as a "task"
**Now:** `reindex` (copying documents to another project) runs synchronously, but still returns a `task` id, and
`get_task_status` reads the result from an in-memory dict. That dict is lost on restart and not shared between server
processes, so the task endpoint only works by accident.
**Better:** either a plain synchronous endpoint that returns the number of copied documents, or (for very large
copies) a real job table with status. Also: the name "reindex" comes from elastic; "copy" describes it better.

### Refresh
**Now:** `GET /index/{ix}/refresh` and the `refresh` parameter of uploads are kept, but do nothing (postgres makes
documents searchable on commit).
**Better:** deprecate and remove.

### Upload operations and the failure format
**Now:** `index` / `create` / `update` / `upsert` with a `{successes, failures}` result, mirroring the elastic bulk
API.
**Better:** fine to keep, but in postgres an upload is one transaction. We could choose all-or-nothing semantics
(clearer for users), and report failures in a more useful format.

### Aggregation pagination (`after`)
**Now:** the `after` cursor is an offset; every page recomputes the whole aggregation and returns rows 1000-2000 etc.
This mimics elastic composite aggregation pagination.
**Better:** aggregations are fast now; return all buckets (with a sane maximum), or let the client set
order/limit (e.g. top 100 values by count), which is what SQL is good at.

### Aggregation result shape
**Now:** the count column is called `n`, which collides with a field called `n`; metric names are `avg_field`, etc.
**Better:** reserved names (e.g. `_n`) or a nested structure.

### Query string syntax
**Now:** Lucene-like syntax with OR as the default operator (like elastic `query_string`), parsed by our own parser.
**Better:** since we own the parser now, we can choose the syntax deliberately: e.g. AND as default (what most users
expect), clear errors for unsupported syntax, and maybe a simpler documented subset. Note: changing the default
operator changes the results of existing queries.

### Snippets
**Now:** snippet parameters (`nomatch_chars`, `max_matches`, `match_chars`) and behaviour copy the elastic highlighter
(e.g. extending the no-match snippet to the end of a word).
**Better:** fine as is, but we are free to define snippets in a way that is simpler to explain to metareaders and
admins (e.g. "N sentences around each match").

### Multiple projects in the URL
**Now:** `/index/a,b,c/query` (comma-separated ids in the path, elastic style).
**Better:** a `projects` list in the request body, and "project" instead of "index" throughout the API (there is
already a TODO for this in `api/index.py`).

### Field stats and values
**Now:** `field_stats` returns elastic's stats shape (`count`, `min`, `max`, `avg`, `sum`, `*_as_string` for dates).
`field_values` returns the most frequent values. Both fine, but could be designed for what the frontend needs.

### Unused parameters
`list_fields(auto_repair=...)` and `create_or_update_systemdata(rm_pending_migrations=...)` are kept for compatibility
but have no meaning anymore.

## Data model

### Roles, requests and object storage refer to projects by text id
**Now:** these tables use the project id string (and `"_server"` for server roles), without foreign keys, like the old
system indices. Deleting a project deletes them explicitly.
**Better:** reference `projects.pk` with `ON DELETE CASCADE` (and a separate server roles table). This also makes it
possible to rename project ids (the pk is the real identity now).

### Guest roles
**Now:** stored as a role with email `*` (and domain roles as `*@domain`), as before.
**Better:** fine, but a `guest_role` column on projects would be simpler to query and explain.

### Server settings and api key restrictions are merged on update
**Now:** updates are merged into the existing jsonb (like elastic partial updates), which means a setting cannot be
removed by leaving it out. Server settings are a single jsonb document.
**Better:** explicit columns or full replacement semantics.

### Field-level visibility
The query parser already supports restricting which fields can be queried (`FieldSet.queryable`), but the API still
uses the old metareader logic, which only restricts which fields are *returned*, not which can be *queried*. This is
where the planned "visible / queryable but invisible / invisible" settings should go.

## Things that are new and could be exposed more
- Renaming fields (`systemdata.fields.rename_field`) has no API endpoint yet.
- Vectors are stored and indexed (pgvector), but there is no similarity search endpoint.
- Copies record provenance (`documents.source`), which is not shown anywhere yet.
