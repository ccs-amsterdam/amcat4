"""Integration tests: need AMCAT4_POSTGRES_TEST_URL (see conftest)"""

from datetime import date

import pytest

from amcat4.models import FilterSpec, SnippetParams
from amcat4.postgres.aggregate import Axis, Metric, aggregate
from amcat4.postgres.documents import copy_documents, get_document, upload_documents
from amcat4.postgres.fields import FieldSet, create_fields, list_fields, rename_field
from amcat4.postgres.projects import create_project
from amcat4.postgres.search import SearchQuery, count, search

pytestmark = pytest.mark.anyio

FIELD_TYPES = {"title": "text", "text": "text", "source": "keyword", "n": "integer", "date": "date", "tags": "tag"}
DOCS = [
    dict(
        _id="1",
        title="The quick brown fox",
        text="jumps over the lazy dog",
        source="news",
        n=5,
        date="2024-03-01T10:00:00",
        tags=["a", "b"],
    ),
    dict(
        _id="2", title="Lazy afternoon", text="with a dog. The dog sleeps.", source="blog", n=12, date="2025-01-15", tags=["b"]
    ),
    dict(
        _id="3", title="Fox news reports", text="Immigration debate continues", source="news", n=7, date="2023-06-01T23:30:00Z"
    ),
]


async def setup_project(conn, project_id="p1", docs=DOCS):
    pk = await create_project(conn, project_id)
    fields = await create_fields(conn, pk, FIELD_TYPES)
    await upload_documents(conn, pk, docs, fields)
    return pk, FieldSet({pk: fields})


async def ids(conn, fs, **kwargs):
    res = await search(conn, fs, SearchQuery(**kwargs), [], per_page=100)
    return sorted(d["_id"] for d in res.results)


async def test_upload_and_get(conn):
    pk, fs = await setup_project(conn)
    doc = await get_document(conn, pk, "1", fs.project_fields[pk])
    assert doc["title"] == "The quick brown fox" and doc["n"] == 5 and doc["tags"] == ["a", "b"]
    assert doc["date"] == "2024-03-01T10:00:00.000000Z"
    # update merges fields
    await upload_documents(conn, pk, [{"_id": "1", "n": 6}], fs.project_fields[pk])
    doc = await get_document(conn, pk, "1", fs.project_fields[pk])
    assert doc["n"] == 6 and doc["title"] == "The quick brown fox"


async def test_query_strings(conn):
    _, fs = await setup_project(conn)
    assert await ids(conn, fs, queries={"q": "fox"}) == ["1", "3"]
    assert await ids(conn, fs, queries={"q": "title:fox"}) == ["1", "3"]
    assert await ids(conn, fs, queries={"q": "dog"}) == ["1", "2"]  # default fields include text
    assert await ids(conn, fs, queries={"q": "fox AND NOT news"}) == ["1"]
    assert await ids(conn, fs, queries={"q": "fox -source:news"}) == []
    assert await ids(conn, fs, queries={"q": "immigr*"}) == ["3"]
    assert await ids(conn, fs, queries={"q": '"quick fox"~1'}) == ["1"]
    assert await ids(conn, fs, queries={"q": '"quick fox"'}) == []
    assert await ids(conn, fs, queries={"q": "foxx~1"}) == ["1", "3"]
    assert await ids(conn, fs, queries={"q": "n:>6"}) == ["2", "3"]
    assert await ids(conn, fs, queries={"q": "n:[5 TO 7]"}) == ["1", "3"]
    assert await ids(conn, fs, queries={"q": "date:>=2024-01-01"}) == ["1", "2"]
    assert await ids(conn, fs, queries={"q": "date:2023-06-01"}) == ["3"]
    assert await ids(conn, fs, queries={"q": "tags:b"}) == ["1", "2"]
    assert await ids(conn, fs, queries={"q": "sour*"}) == []
    assert await ids(conn, fs, queries={"q": "source:ne*"}) == ["1", "3"]


async def test_filters(conn):
    _, fs = await setup_project(conn)
    f = FilterSpec
    assert await ids(conn, fs, filters={"source": f(values=["news"])}) == ["1", "3"]
    assert await ids(conn, fs, filters={"n": f(gt=5, lte=12)}) == ["2", "3"]
    assert await ids(conn, fs, filters={"date": f(gte="2024-01-01")}) == ["1", "2"]
    assert await ids(conn, fs, filters={"date": f(lt="2024-01-01")}) == ["3"]
    assert await ids(conn, fs, filters={"tags": f(exists=True)}) == ["1", "2"]
    assert await ids(conn, fs, filters={"tags": f(exists=False)}) == ["3"]
    assert await ids(conn, fs, filters={"date": f(monthnr=3)}) == ["1"]
    assert await ids(conn, fs, filters={"date": f(dayofweek="Wednesday")}) == ["2"]
    assert await ids(conn, fs, queries={"q": "fox"}, filters={"source": f(values=["news"]), "n": f(lt=6)}) == ["1"]
    assert await count(conn, fs, SearchQuery(filters={"source": f(values=["news"])})) == 2


async def test_projects_are_separate_and_cross_project(conn):
    pk1, fs1 = await setup_project(conn, "p1")
    pk2, fs2 = await setup_project(conn, "p2", DOCS[:1])
    assert await ids(conn, fs1, queries={"q": "fox"}) == ["1", "3"]
    assert await ids(conn, fs2, queries={"q": "fox"}) == ["1"]
    both = FieldSet({pk1: fs1.project_fields[pk1], pk2: fs2.project_fields[pk2]})
    assert await ids(conn, both, queries={"q": "title:fox"}) == ["1", "1", "3"]
    assert await ids(conn, both, filters={"n": FilterSpec(values=[5])}) == ["1", "1"]


async def test_visibility(conn):
    pk, _ = await setup_project(conn)
    fields = await list_fields(conn, pk)
    fs = FieldSet({pk: fields}, queryable={"title", "source"})
    assert await ids(conn, fs, queries={"q": "dog"}) == []  # text is not a default field for this user
    with pytest.raises(ValueError):
        await ids(conn, fs, queries={"q": "text:dog"})


async def test_sort_and_paginate(conn):
    _, fs = await setup_project(conn)
    res = await search(conn, fs, SearchQuery(), ["title"], sort=[("date", "desc")], per_page=2)
    assert [d["_id"] for d in res.results] == ["2", "1"] and res.total == 3
    res = await search(conn, fs, SearchQuery(), ["title"], sort=[("date", "desc")], per_page=2, page=1)
    assert [d["_id"] for d in res.results] == ["3"]
    res = await search(conn, fs, SearchQuery(), ["n"], sort=[("n", "asc")])
    assert [d["n"] for d in res.results] == [5, 7, 12]


async def test_snippets_and_highlight(conn):
    _, fs = await setup_project(conn)
    params = SnippetParams(nomatch_chars=5, max_matches=1, match_chars=10)
    res = await search(conn, fs, SearchQuery(queries={"q": "dog"}), ["title"], snippets={"text": params})
    snippets = {d["_id"]: d["text"] for d in res.results}
    assert "dog" in snippets["1"] and len(snippets["1"]) <= 10
    res = await search(conn, fs, SearchQuery(queries={"q": "title:fox"}), ["title"], snippets={"text": params})
    assert {d["_id"]: d["text"] for d in res.results}["1"] == "jumps"  # no match in text: first 5 chars
    res = await search(conn, fs, SearchQuery(queries={"q": "fox"}), ["title"], highlight=True)
    assert {d["_id"]: d["title"] for d in res.results}["1"] == "The quick brown <em>fox</em>"


async def test_aggregate(conn):
    _, fs = await setup_project(conn)
    rows = await aggregate(conn, fs, SearchQuery(), [Axis("source")])
    assert rows == [{"source": "blog", "n": 1}, {"source": "news", "n": 2}]
    rows = await aggregate(conn, fs, SearchQuery(), [Axis("date", "year")], [Metric("n", "avg")])
    assert [(r["date_year"], r["n"], r["avg_n"]) for r in rows] == [
        (date(2023, 1, 1), 1, 7.0),
        (date(2024, 1, 1), 1, 5.0),
        (date(2025, 1, 1), 1, 12.0),
    ]
    rows = await aggregate(conn, fs, SearchQuery(queries={"q": "dog"}), [Axis("tags")])
    assert rows == [{"tags": "a", "n": 1}, {"tags": "b", "n": 2}]
    rows = await aggregate(conn, fs, SearchQuery(queries={"fox": "fox", "dog": "dog"}), [Axis("_query"), Axis("source")])
    assert {(r["_query"], r["source"], r["n"]) for r in rows} == {("fox", "news", 2), ("dog", "news", 1), ("dog", "blog", 1)}
    rows = await aggregate(conn, fs, SearchQuery(), [Axis("date", "dayofweek")])
    assert {r["date_dayofweek"] for r in rows} == {"Friday", "Wednesday", "Thursday"}
    rows = await aggregate(conn, fs, SearchQuery(), [], [Metric("date", "max")])
    assert rows[0]["n"] == 3 and rows[0]["max_date"].year == 2025


async def test_rename_field_is_metadata_only(conn):
    pk, _ = await setup_project(conn)
    await rename_field(conn, pk, "title", "headline")
    fs = FieldSet({pk: await list_fields(conn, pk)})
    assert await ids(conn, fs, queries={"q": "headline:fox"}) == ["1", "3"]


async def test_unique_fields(conn):
    pk = await create_project(conn, "p1")
    fields = await create_fields(conn, pk, {"url": "keyword", "title": "text"}, unique_fields=["url"])
    await upload_documents(conn, pk, [{"url": "a", "title": "first"}, {"url": "b", "title": "x"}], fields)
    await upload_documents(conn, pk, [{"url": "a", "title": "second"}, {"url": "a", "title": "third"}], fields)
    fs = FieldSet({pk: fields})
    res = await search(conn, fs, SearchQuery(), ["url", "title"], sort=[("url", "asc")])
    assert [(d["url"], d["title"]) for d in res.results] == [("a", "third"), ("b", "x")]
    await upload_documents(conn, pk, [{"url": "a", "title": "fourth"}], fields, on_conflict="skip")
    res = await search(conn, fs, SearchQuery(queries={"q": "url:a"}), ["title"])
    assert res.results[0]["title"] == "third"


async def test_copy_subset(conn):
    pk1, fs1 = await setup_project(conn, "p1")
    pk2 = await create_project(conn, "copy")
    src = fs1.project_fields[pk1]
    dest = await create_fields(conn, pk2, {"headline": "text", "source": "keyword"})
    from psycopg.types.json import Jsonb

    from amcat4.postgres.search import compile_search

    c = compile_search(fs1, SearchQuery(queries={"q": "fox"}))
    n = await copy_documents(
        conn,
        pk1,
        pk2,
        {src["title"]: dest["headline"], src["source"]: dest["source"]},
        where_sql="id @@@ %s::jsonb",
        where_params=[Jsonb(c.json_query)],
    )
    assert n == 2
    fs2 = FieldSet({pk2: dest})
    res = await search(conn, fs2, SearchQuery(queries={"q": "headline:fox"}), ["headline", "source"])
    assert sorted(d["_id"] for d in res.results) == ["1", "3"]
    with pytest.raises(ValueError):
        await ids(conn, fs2, queries={"q": "text:dog"})  # text was not copied


async def test_update_and_delete_by_query(conn):
    from amcat4.postgres.documents import delete_by_query, update_by_query, update_tag_by_query

    pk, fs = await setup_project(conn)
    fields = fs.project_fields[pk]
    assert await update_tag_by_query(conn, fs, SearchQuery(queries={"q": "fox"}), fields["tags"], "c", "add") == 2
    assert await update_tag_by_query(conn, fs, SearchQuery(queries={"q": "fox"}), fields["tags"], "c", "add") == 0
    assert await ids(conn, fs, queries={"q": "tags:c"}) == ["1", "3"]
    assert await update_tag_by_query(conn, fs, SearchQuery(), fields["tags"], "b", "remove") == 2
    doc = await get_document(conn, pk, "2", fields)
    assert "tags" not in doc
    assert await update_by_query(conn, fs, SearchQuery(ids=["1", "2"]), fields["source"], "wire") == 2
    assert await ids(conn, fs, filters={"source": FilterSpec(values=["wire"])}) == ["1", "2"]
    assert await update_by_query(conn, fs, SearchQuery(ids=["1"]), fields["source"], None) == 1
    assert await ids(conn, fs, filters={"source": FilterSpec(exists=False)}) == ["1"]
    assert await delete_by_query(conn, fs, SearchQuery(queries={"q": "dog"})) == 2
    assert await ids(conn, fs) == ["3"]


async def test_snippets_non_ascii(conn):
    docs = [dict(_id="u", title="Café über déjà vu fox", text="x")]
    _, fs = await setup_project(conn, docs=docs)
    res = await search(conn, fs, SearchQuery(queries={"q": "fox"}), ["title"], highlight=True)
    assert res.results[0]["title"] == "Café über déjà vu <em>fox</em>"


async def test_primary_date_and_derived_keys(conn):
    from amcat4.postgres.documents import update_by_query

    pk, fs = await setup_project(conn)
    fields = fs.project_fields[pk]
    assert fields["date"].primary_date
    cur = await conn.execute("SELECT doc_id, sort_date FROM documents ORDER BY doc_id")
    assert [r["sort_date"].year for r in await cur.fetchall()] == [2024, 2025, 2023]
    rows = await aggregate(conn, fs, SearchQuery(), [Axis("date", "month")])
    assert [(r["date_month"], r["n"]) for r in rows] == [(date(2023, 6, 1), 1), (date(2024, 3, 1), 1), (date(2025, 1, 1), 1)]
    rows = await aggregate(conn, fs, SearchQuery(), [Axis("date", "monthnr")])
    assert [r["date_monthnr"] for r in rows] == [1, 3, 6]
    # updating the date updates sort_date and derived keys
    assert await update_by_query(conn, fs, SearchQuery(ids=["3"]), fields["date"], "2026-12-31T12:00:00Z") == 1
    assert await ids(conn, fs, filters={"date": FilterSpec(monthnr=12)}) == ["3"]
    res = await search(conn, fs, SearchQuery(), [], sort=[("date", "desc")])
    assert [d["_id"] for d in res.results] == ["3", "2", "1"]
