# Elastic vs Postgres: trade-offs

Here are some of my notes, proof-read and copy-edited by claude :)

## 1. Why move away from Elastic at all?

Elasticsearch is a great search engine, but we were also using it as our database.

**We stored data in Elastic that it isn't suited for**
Besides the documents, all our system data lived in Elastic indices: users and roles, API keys, server and project
settings, field definitions, role requests:
- No transactions. Creating a project, its fields and its admin role are separate writes, so a failure halfway leaves
  a half-created project. Same for deleting, or changing a field type on documents that are being uploaded.
- No relations or constraints. Elastic can't enforce that a role points to an existing project, or that a name
  is unique, so all of that is checked (or forgotten) in our own code.
- Writes are near real-time: they only become visible after a refresh (by default about once per second). For
  things like permissions and API keys you really want "if it's saved, it's true".

For security and stability (who can see what, and data that is never half-written) we need transactions and
relational data. 

**We had our own migration system**
Changing the structure of the system data meant creating a new version of the system indices (`v1`, `v2`, ...),
copying all data over, and tracking pending and broken migrations, with a custom runner for all of that. In Postgres
we use Alembic, the standard tool for this, and schema changes themselves run in transactions.

**Elastic seemed expensive, and built for something else**
Elastic needs a lot of memory (heap, plus memory for the file cache) and works best on a cluster of nodes. It is
built for high-performance analytics on large amounts of data (logs, metrics, big search applications). AmCAT is
(or is becoming?) more about long-term storage and secure sharing of research data, with many small projects and a few big ones.
Postgres seems is a better fit for that.


The catch is that we still need good full-text search. The goal of this migration was to also test whether postgres can handle this, instead of combining it with a separate search enging (like ElasticSearch). Thats what the following points are about.


## 2. Querying

Using pg_search in postgres works pretty great, and we can do almost anything elasticsearch does. It's also fast: in a benchmark with 1M documents (on a desktop with untuned settings), most searches and filters take 5-30 ms, and things that touch (almost) all documents of a 500k document project (counting a very common word, sorting everything by date, aggregating the whole project) ~100-250 ms. The catch is that the index needs some maintenance: after uploads it's split into many small pieces, and after mass updates (e.g. changing every document of a big project) it grows a lot. A reindex fixes both (online, ~7 seconds per 1M documents) and makes most searches 2-3x faster, so we should probably run it automatically after large uploads and updates. See the [benchmark](benchmark/README.md) for the details (and the open issues). However there some limitations, and some complications (that do also come with some benefits).

**Query/aggretate/sort support compared to elastic**
- Our parser only supports trailing wildcards like `econom*`, not `*nom?es` type stuff (which was also expensive in elastic). pg_search does have a regex query, but in our tests it doesn't work properly on jsonb fields (it ignores which field you ask for), so we can't easily add this anyway. And I think this is a fair limiatation that avoids people like Jan Kleinnijenhuis performing impossibly expensive queries and killing poor AmCAT.
- While querying on jsonb fields is fast, sorting on them is slow: pg_search's fast Top-K sorting doesn't support json keys ("not yet supported", according to their docs), so it has to read all matching documents first.
- pg_search can't aggregate on calendar units like month or year inside the index (its date histogram only seems to support fixed intervals). Claude now just splits a date type field into multiple fields for year, month, weekday. This is a decent compromise, and we could keep the nr of options limited to things the client could aggregate themselves. 

About the sorting thing. I do expect that pg_search will address this at some point, so we shouldn't over engineer a solution. The question is whether to support slow (expensive) sort until then. Alternatively, what could make sense is to have some standard fields in amcat that are regular columns in the documents table, like 'date' and 'source'. These would then support sorting, and some standard columns would also make sense for data discovery purposes.

**pg_search is young-ish**
The pg_search extension (by ParadeDB) is popular, [well funded](https://dealroom.co/companies/paradedb/) and ready to be used in production, but it's also fairly young (2023) and in active development. It looks safe to bet on, but we might see some API changes every now and then.

There is also quite some competition on getting lucene into postgres. So I'm quite optimistic about just having postgres handle both the database and search engine. There is the issue of how to maintain a stable query syntax in AmCAT though. Which brings us to...

**A custom query parser...**
while pg_search does come with its own query parser, Claude decided it wasn't good enough, and just build a completely new one...
I would have been very much against this 2 years ago. But seeing how quickly Claude built a proper parser with unit tests and all, I think having our own query parser might actually be worth considering: 

- If we ever need to change the search backend, AmCAT's query logic wont change.
- In this case, the query parser allowed using the same lucene style elastic uses, and was also needed to make some features work on the jsonb fields.
- We can limit what features people can use. Like not supporting expensive operations like regex.
- Custom (social scientist friendly) error messages. E.g. that "house parli*"~4 is not supported.
- We needed some query processing anyway for decoupling the field ids from the given field names.
- We control which fields can be queried (field-level access). This is a good addition to our access control. We currently only supported not letting some roles 'see' a field, but some fields should also not be queryable for them.

**Querying multiple projects:** the same field name has a different key per project, so the query is expanded per
project: a bare word becomes one clause per text field per project, so 100 projects with 3 text fields each give
300 clauses. Plain words are probably still cheap (each clause is a quick lookup), but prefix and fuzzy queries,
and touching many partitions, get expensive. We haven't measured this yet. I think we'd limit multi-project queries
to two cases anyway:
- **Specific multi-project queries** (normal search, with ranking, snippets, sorting and paging), with a limit on the
  number of projects (say a few dozen). That keeps both the expanded query and the number of partitions small.
- **Server-wide exploration**, e.g. the number of documents per project (overall, or for a query). These are only
  counts, so we can run them in batches, one partition at a time, and add up the results. The `date` and `source`
  columns need no expansion at all, so things like "documents per source per month" are cheap. These should only
  return counts (not documents) for projects you can't read, and could run as background jobs and be cached.

**How are fields stored?** fields live in three jsonb columns: `text_fields` (text, tokenized), `exact_fields` (keywords, numbers, dates, tags: exact)
or `stored_fields` (objects, stored but not indexed). Vectors are also supported (pg_vector), and kept in a separate table.
You can change field types, which either: 
- just changes the field metadata (keyword to image; just for amcat to know this is a URL)
- overwrites the value (keyword -> number; if coercion fails the transaction cancels),
- moves the value to the right column (keyword -> text will remove it from exact_fields and create in text_fields)


## 3. Managing (BM25) indices

Wouter tells me not to worry about this, but I'll try to convince you why its important, and not just interesting.

**What is a BM25 index?**
The search index behind both Elastic and pg_search. Both are built on the same idea (Elastic uses Lucene, pg_search uses Tantivy, a Rust search library inspired by Lucene).
- **Elastic:** an index is split into one or more *shards*. Each shard is a complete Lucene index of its own, with its own BM25 statistics.
- **pg_search:** one BM25 index per table (the docs say a table can only have one). If the table is partitioned, every partition gets its own BM25 index. So partitions are roughly like "shards".

**Why should we care?** How we split data over BM25 indices determines:
- how expensive AmCAT is to host, and how well it scales (very important)
- how stable AmCAT is when uploading data (very important)
- how fast, safe (and complicated) it is to query across projects (the 'safe' part is important)
- how fast queries are (mildly important)

**Elastic: one index per project**
We needed this for custom field names and types per project. Downsides:
- Every project is at least one shard, and every shard has a fixed overhead (heap memory, files, and a search thread per shard per query), even when small or idle. Elastic recommends shards of 10-50GB, and by default allows at most 1000 shards per node. (There used to be a rule of thumb of max ~20 shards per GB of heap. Newer docs seem to have dropped it, and count overhead per index and per mapped field instead, which doesn't really help us either.)
- This is not ideal for AmCAT, which has a long tail of project sizes. Especially if we encourage copying projects.
- Querying across indices sends the query to every shard (each searched by a single thread) and merges the results. There are no locks, but the cost grows with the number of shards, and it has to deal with conflicting field types and permissions.
- In short, the problem is that there is a functional relation between projects and indices. We use indices to isolate field names and types. This complicates using indices for performance and querying across indices. 
 
**Postgres: all projects in one table, one index per partition, projects can share partitions**
We now designed postgres with pg_seach in a way that all projects can be in the same table, and functionally could all share one big index. We only need to distribute them over partitions (that get their own index) for better performance and efficiency (querying, reindexing).

- Fields are stored in jsonb columns under stable keys (`f14`, `f600`) that point to a `fields` table, so field names
and types are per project while projects share the same table and BM25 index. This seems to only add a bit of storage overhead, because the jsonb values are indexed together with the field ids. As a side benefit, it makes it easy to rename and retype columns. 
- We can then use different strategies for distributing projects over partitions. Partitions seem to have less overhead than Elastic shards (an empty partition with its index is ~2.8MB on disk, and as far as I can tell memory is only used for what is actually queried), but it's still good to limit them. In particular, because this avoids issues when querying across all projects (which we need to support data exploration) 
- The strategy I now use is that projects get assigned to a partition id on create, and we add a new partition when the current partition exceeds a given size (now 5GB). We then don't think about it anymore. If poorly balanced partitions ever becomes an issue, or we decide its better to group specific projects together, it would be easy to add a feature for move projects across partitions. 

**One small note**: projects within a partition do share the BM25 statistics for how rare a word is (idf). This is not ideal because it creates a weird interaction, but its fairly harmless (only affects ranking, not which documents match). Elastic also computes these per shard by default (`dfs_query_then_fetch` collects global statistics first, but Elastic advises against it in production). The difference is that in Elastic each project had its own index, so other projects never affected its scores. Elastic's docs do say these differences even out once there is enough data, which would also hold for our partitions.
