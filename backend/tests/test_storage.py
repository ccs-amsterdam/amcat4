"""
Tests for storage features of the postgres backend: query syntax, filters, sort slots, renaming fields,
vectors, geo points, copies and identifiers.
"""

import pytest

from amcat4.errors import NotFoundError
from amcat4.models import CreateDocumentField, FieldSpec, FilterSpec, ProjectSettings, SnippetParams, UpdateDocumentField
from amcat4.postgres.connection import fetch_all
from amcat4.projects.aggregate import Axis, query_aggregate
from amcat4.projects.documents import create_or_update_documents, fetch_document
from amcat4.projects.index import create_project_index
from amcat4.projects.query import delete_query, query_documents, reindex, update_query, update_tag_query
from amcat4.systemdata.fields import list_fields, rename_field, update_fields

FIELDS = {"title": "text", "text": "text", "source": "keyword", "n": "integer", "date": "date", "tags": "tag"}
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


async def ids(index, q=None, filters=None, **kwargs) -> list[str]:
    res = await query_documents(index, queries={"q": q} if q else None, filters=filters, per_page=100, **kwargs)
    return sorted(d["_id"] for d in res.data) if res else []


@pytest.fixture
async def docs_index(index):
    await create_or_update_documents(index, DOCS, FIELDS)
    return index


@pytest.mark.anyio
async def test_query_syntax(docs_index):
    q = docs_index
    assert await ids(q, "fox") == ["1", "3"]
    assert await ids(q, "title:fox") == ["1", "3"]
    assert await ids(q, "dog") == ["1", "2"]
    assert await ids(q, "fox AND NOT news") == ["1"]
    assert await ids(q, "fox -source:news") == []
    assert await ids(q, "immigr*") == ["3"]
    assert await ids(q, '"quick fox"~1') == ["1"]
    assert await ids(q, '"quick fox"') == []
    assert await ids(q, "foxx~1") == ["1", "3"]
    assert await ids(q, "n:>6") == ["2", "3"]
    assert await ids(q, "n:[5 TO 7]") == ["1", "3"]
    assert await ids(q, "date:>=2024-01-01") == ["1", "2"]
    assert await ids(q, "date:2023-06-01") == ["3"]
    assert await ids(q, "tags:b") == ["1", "2"]
    assert await ids(q, "source:ne*") == ["1", "3"]


@pytest.mark.anyio
async def test_filters(docs_index):
    f = FilterSpec
    q = docs_index
    assert await ids(q, filters={"source": f(values=["news"])}) == ["1", "3"]
    assert await ids(q, filters={"n": f(gt=5, lte=12)}) == ["2", "3"]
    assert await ids(q, filters={"date": f(gte="2024-01-01")}) == ["1", "2"]
    assert await ids(q, filters={"date": f(lt="2024-01-01")}) == ["3"]
    assert await ids(q, filters={"tags": f(exists=True)}) == ["1", "2"]
    assert await ids(q, filters={"tags": f(exists=False)}) == ["3"]
    assert await ids(q, filters={"text": f(exists=True)}) == ["1", "2", "3"]
    assert await ids(q, filters={"date": f(monthnr=3)}) == ["1"]
    assert await ids(q, filters={"date": f(dayofweek="Wednesday")}) == ["2"]
    assert await ids(q, "fox", filters={"source": f(values=["news"]), "n": f(lt=6)}) == ["1"]


@pytest.mark.anyio
async def test_snippets_non_ascii(index):
    await create_or_update_documents(index, [dict(_id="u", title="Café über déjà vu fox")], {"title": "text"})
    res = await query_documents(index, fields=[FieldSpec(name="title")], queries={"q": "fox"}, highlight=True)
    assert res and res.data[0]["title"] == "Café über déjà vu <em>fox</em>"
    res = await query_documents(
        index, fields=[FieldSpec(name="title", snippet=SnippetParams(max_matches=1, match_chars=3))], queries={"q": "fox"}
    )
    assert res and res.data[0]["title"] == "fox"


@pytest.mark.anyio
async def test_sort_slots(docs_index):
    async def order(field, direction="asc"):
        res = await query_documents(docs_index, sort=[{field: {"order": direction}}], per_page=10)  # type: ignore
        return [d["_id"] for d in res.data] if res else []

    fields = await list_fields(docs_index)
    assert fields["date"].sort_slot == "date"  # the first date field gets the date slot
    assert fields["n"].sort_slot is None
    assert await order("date", "desc") == ["2", "1", "3"]
    assert await order("n") == ["1", "3", "2"]  # sorting on fields without slot also works

    await update_fields(docs_index, {"n": UpdateDocumentField(fast_sort=True)})
    assert (await list_fields(docs_index))["n"].sort_slot == "number"
    assert await order("n", "desc") == ["2", "3", "1"]
    # new documents also fill the sort column
    await create_or_update_documents(docs_index, [dict(_id="4", title="new", n=100)])
    assert (await order("n", "desc"))[0] == "4"
    with pytest.raises(ValueError):
        await update_fields(docs_index, {"title": UpdateDocumentField(fast_sort=True)})


@pytest.mark.anyio
async def test_rename_field(docs_index):
    await rename_field(docs_index, "title", "headline")
    assert await ids(docs_index, "headline:fox") == ["1", "3"]
    doc = await fetch_document(docs_index, "1")
    assert doc["headline"] == "The quick brown fox" and "title" not in doc
    with pytest.raises(ValueError):
        await rename_field(docs_index, "text", "headline")


@pytest.mark.anyio
async def test_vectors(index):
    fields = {"text": "text", "embedding": "vector"}
    docs = [dict(_id="a", text="x", embedding=[1, 0, 0]), dict(_id="b", text="y", embedding=[0.5, 0.5, 0])]
    await create_or_update_documents(index, docs, fields)
    assert (await fetch_document(index, "a"))["embedding"] == [1.0, 0.0, 0.0]
    res = await query_documents(index, fields=[FieldSpec(name="embedding")], sort=[{"_id": {"order": "asc"}}])  # type: ignore
    assert res and [d["embedding"] for d in res.data] == [[1.0, 0.0, 0.0], [0.5, 0.5, 0.0]]
    # each field has a vector index, which fixes the number of dimensions
    indexes = await fetch_all("SELECT indexname FROM pg_indexes WHERE tablename = 'document_vectors'")
    assert any(i["indexname"].startswith("document_vectors_f") for i in indexes)
    with pytest.raises(Exception):
        await create_or_update_documents(index, [dict(_id="c", embedding=[1, 2])])


@pytest.mark.anyio
async def test_geo(index):
    docs = [
        dict(_id="ams", location={"lat": 52.37, "lon": 4.89}),
        dict(_id="nyc", location="40.71,-74.0"),
        dict(_id="syd", location=[151.2, -33.87]),  # [lon, lat], like elastic
    ]
    await create_or_update_documents(index, docs, {"location": "geo_point"})
    assert (await fetch_document(index, "nyc"))["location"] == {"lat": 40.71, "lon": -74.0}
    assert await ids(index, "location.lat:>45") == ["ams"]
    assert await ids(index, filters={"location.lon": FilterSpec(lt=0)}) == ["nyc"]
    assert await ids(index, filters={"location.lat": FilterSpec(lt=0), "location.lon": FilterSpec(gt=100)}) == ["syd"]
    with pytest.raises(ValueError):
        await create_or_update_documents(index, [dict(_id="bad", location={"lat": 100, "lon": 0})])


@pytest.mark.anyio
async def test_identifiers(index):
    fields = {"url": CreateDocumentField(type="keyword", identifier=True), "title": CreateDocumentField(type="text")}
    await create_or_update_documents(index, [dict(url="a", title="first"), dict(url="b", title="x")], fields)
    await create_or_update_documents(index, [dict(url="a", title="second"), dict(url="a", title="third")])
    res = await query_documents(
        index, fields=[FieldSpec(name="url"), FieldSpec(name="title")], sort=[{"url": {"order": "asc"}}]
    )  # type: ignore
    assert res and [(d["url"], d["title"]) for d in res.data] == [("a", "third"), ("b", "x")]
    result = await create_or_update_documents(index, [dict(url="a", title="fourth")], op_type="create")
    assert result["successes"] == 0 and len(result["failures"]) == 1


@pytest.mark.anyio
async def test_update_and_delete_by_query(docs_index):
    q = docs_index
    assert (await update_tag_query(q, "add", "tags", "c", queries={"q": "fox"}))["updated"] == 2
    assert (await update_tag_query(q, "add", "tags", "c", queries={"q": "fox"}))["updated"] == 0
    assert await ids(q, "tags:c") == ["1", "3"]
    assert (await update_tag_query(q, "remove", "tags", "b"))["updated"] == 2
    assert "tags" not in await fetch_document(q, "2")
    assert (await update_query(q, "source", "wire", ids=["1", "2"]))["updated"] == 2
    assert await ids(q, filters={"source": FilterSpec(values=["wire"])}) == ["1", "2"]
    assert (await update_query(q, "date", "2026-12-31T12:00:00Z", ids=["3"]))["updated"] == 1
    assert await ids(q, filters={"date": FilterSpec(monthnr=12)}) == ["3"]  # derived keys are updated
    res = await query_documents(q, sort=[{"date": {"order": "desc"}}])  # type: ignore
    assert res and res.data[0]["_id"] == "3"  # sort column is updated
    assert (await delete_query(q, queries={"q": "dog"}))["updated"] == 2
    assert await ids(q) == ["3"]


@pytest.mark.anyio
async def test_copy_subset(docs_index, index_name):
    await create_project_index(ProjectSettings(id=index_name))
    await reindex(
        docs_index,
        index_name,
        queries={"q": "fox"},
        field_options={"title": {"rename": "headline"}, "text": {"exclude": True}},
    )
    assert await ids(index_name) == ["1", "3"]
    doc = await fetch_document(index_name, "1")
    assert doc["headline"] == "The quick brown fox" and "text" not in doc
    assert await ids(index_name, filters={"date": FilterSpec(monthnr=3)}) == ["1"]
    rows = await fetch_all(
        "SELECT source FROM documents d JOIN projects p ON p.pk = d.project_pk WHERE p.id = %s", [index_name]
    )
    assert {r["source"]["doc_id"] for r in rows} == {"1", "3"}  # provenance


@pytest.mark.anyio
async def test_aggregate_tags_and_multi_project(docs_index, index_name):
    rows = (await query_aggregate(docs_index, [Axis("tags")])).as_dicts()
    assert list(rows) == [{"tags": "a", "n": 1}, {"tags": "b", "n": 2}]
    # A second project, with the same field names (but different field keys)
    await create_project_index(ProjectSettings(id=index_name))
    await create_or_update_documents(index_name, [dict(_id="x", title="Another fox", source="tv")], FIELDS)
    assert await ids([docs_index, index_name], "title:fox") == ["1", "3", "x"]
    result = await query_aggregate([docs_index, index_name], [Axis("source")])
    assert list(result.as_dicts()) == [{"source": "blog", "n": 1}, {"source": "news", "n": 2}, {"source": "tv", "n": 1}]


@pytest.mark.anyio
async def test_not_found(index):
    with pytest.raises(NotFoundError):
        await fetch_document(index, "nonexisting")
    with pytest.raises(NotFoundError):
        await list_fields("nonexisting_index")
