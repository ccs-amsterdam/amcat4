from datetime import datetime

import pytest

from amcat4.models import CreateDocumentField, FieldSpec
from amcat4.projects.documents import (
    create_or_update_documents,
    delete_documents_by_query,
    fetch_document,
    update_document,
    update_document_tag_by_query,
    update_documents_by_query,
)
from amcat4.projects.index import refresh_index
from amcat4.projects.query import query_documents
from amcat4.systemdata.fields import create_fields, field_values, list_fields
from tests.conftest import upload


@pytest.mark.anyio
async def test_upload_retrieve_document(index):
    """Can we upload and retrieve documents"""
    a = dict(
        text="text",
        title="title",
        date="2021-03-09",
        _id="test",
        term_tfidf=[{"term": "test", "value": 0.2}, {"term": "value", "value": 0.3}],
    )
    await create_or_update_documents(
        index, [a], fields={"text": "text", "title": "text", "date": "date", "term_tfidf": "object"}
    )
    await refresh_index(index)
    d = await fetch_document(index, "test")
    assert d["title"] == a["title"]
    assert d["term_tfidf"] == a["term_tfidf"]
    # TODO: should a['date'] be a datetime?


@pytest.mark.anyio
async def test_data_coerced(index):
    """Are field values coerced to the correct field type"""
    await create_fields(index, {"i": "integer", "x": "number", "title": "text", "date": "date", "text": "text"})
    a = dict(_id="DoccyMcDocface", text="text", title="test-numeric", date="2022-12-13", i="1", x="1.1")
    await create_or_update_documents(index, [a])
    d = await fetch_document(index, "DoccyMcDocface")
    assert isinstance(d["i"], int)
    a = dict(text="text", title=1, date="2022-12-13")
    await create_or_update_documents(index, [a])
    d = await fetch_document(index, "DoccyMcDocface")
    assert isinstance(d["title"], str)


@pytest.mark.anyio
async def test_fields(index):
    """Can we get the fields from an index"""
    await create_fields(index, {"title": "text", "date": "date", "text": "text", "url": "keyword"})
    fields = await list_fields(index)
    assert set(fields.keys()) == {"title", "date", "text", "url"}
    assert fields["title"].type == "text"
    assert fields["date"].type == "date"

    # default settings
    assert fields["date"].identifier is False
    assert fields["date"].client_settings is not None

    # By default no metareader access
    assert fields["date"].metareader.access == "none"
    assert fields["text"].metareader.access == "none"


@pytest.mark.anyio
async def test_values(index):
    """Can we get values for a specific field"""
    await upload(index, [dict(bla=x) for x in ["odd", "even", "even"] * 10], fields={"bla": "keyword"})
    assert set(await field_values(index, "bla", 10)) == {"odd", "even"}


@pytest.mark.anyio
async def test_update(index_docs):
    """Can we update a field on a document?"""
    await create_fields(index_docs, {"annotations": "object"})
    assert await fetch_document(index_docs, "0", _source=["annotations"]) == {}
    await update_document(index_docs, "0", {"annotations": {"x": 3}})
    assert (await fetch_document(index_docs, "0", _source=["annotations"]))["annotations"] == {"x": 3}


@pytest.mark.anyio
async def test_update_by_query(index_docs):
    async def cats():
        res = await query_documents(index_docs, fields=[FieldSpec(name="cat"), FieldSpec(name="subcat")])
        return {doc["_id"]: doc.get("subcat") for doc in (res.data if res else [])}

    assert await cats() == {"0": "x", "1": "x", "2": "y", "3": "y"}
    await update_documents_by_query(index_docs, query=dict(term={"cat": dict(value="a")}), field="subcat", value="z")
    assert await cats() == {"0": "z", "1": "z", "2": "z", "3": "y"}
    await update_documents_by_query(index_docs, query=dict(term={"cat": dict(value="b")}), field="subcat", value=None)
    assert await cats() == {"0": "z", "1": "z", "2": "z", "3": None}
    assert "subcat" not in (await fetch_document(index_docs, "3")).keys()


@pytest.mark.anyio
async def test_delete_by_query(index_docs):
    async def ids():
        await refresh_index(index_docs)
        res = await query_documents(index_docs)
        return {doc["_id"] for doc in (res.data if res else [])}

    assert await ids() == {"0", "1", "2", "3"}
    await delete_documents_by_query(index_docs, query=dict(term={"cat": dict(value="a")}))
    assert await ids() == {"3"}


@pytest.mark.anyio
async def test_add_tag(index_docs):
    def q(*ids):
        return dict(query=dict(ids={"values": ids}))

    async def tags():
        res = await query_documents(index_docs, fields=[FieldSpec(name="tag")])
        return {doc["_id"]: doc["tag"] for doc in (res.data if res else []) if "tag" in doc and doc["tag"] is not None}

    assert await tags() == {}
    await update_document_tag_by_query(index_docs, "add", q("0", "1"), "tag", "x")
    await refresh_index(index_docs)
    assert await tags() == {"0": ["x"], "1": ["x"]}
    await update_document_tag_by_query(index_docs, "add", q("1", "2"), "tag", "x")
    await refresh_index(index_docs)
    assert await tags() == {"0": ["x"], "1": ["x"], "2": ["x"]}
    await update_document_tag_by_query(index_docs, "add", q("2", "3"), "tag", "y")
    await refresh_index(index_docs)
    assert await tags() == {"0": ["x"], "1": ["x"], "2": ["x", "y"], "3": ["y"]}
    await update_document_tag_by_query(index_docs, "remove", q("0", "2", "3"), "tag", "x")
    await refresh_index(index_docs)
    assert await tags() == {"1": ["x"], "2": ["y"], "3": ["y"]}


@pytest.mark.anyio
async def test_upload_without_identifiers(index):
    doc = {"title": "titel", "text": "text", "date": datetime(2020, 1, 1)}
    res = await create_or_update_documents(index, [doc], fields={"title": "text", "text": "text", "date": "date"})
    assert res["successes"] == 1
    await _assert_n(index, 1)

    # this doesnt identify duplicates
    res = await create_or_update_documents(index, [doc])
    assert res["successes"] == 1
    await _assert_n(index, 2)


@pytest.mark.anyio
async def test_upload_with_explicit_ids(index):
    doc = {"_id": "1", "title": "titel", "text": "text", "date": datetime(2020, 1, 1)}
    res = await create_or_update_documents(index, [doc], fields={"title": "text", "text": "text", "date": "date"})
    assert res["successes"] == 1
    assert (await fetch_document(index, "1"))["text"] == "text"

    # uploading a doc with same id should replace the existing document
    doc = {"_id": "1", "title": "new title", "date": datetime(2020, 1, 1)}
    res = await create_or_update_documents(index, [doc])
    assert res["successes"] == 1
    await _assert_n(index, 1)
    assert (await fetch_document(index, "1"))["title"] == "new title"


@pytest.mark.anyio
async def test_upload_with_identifiers(index):
    doc = {"url": "http://", "text": "text"}
    res = await create_or_update_documents(
        index, [doc], fields={"url": CreateDocumentField(type="keyword", identifier=True), "text": "text"}
    )
    assert res["successes"] == 1
    await _assert_n(index, 1)

    # Re-uploading a document with the same identifier should update the document
    doc2 = {"url": "http://", "text": "text2"}
    res = await create_or_update_documents(index, [doc2])
    assert res["successes"] == 1
    await _assert_n(index, 1)
    res = await query_documents(index, fields=[FieldSpec(name="text")])
    assert {doc["text"] for doc in (res.data if res else [])} == {"text2"}

    doc3 = {"url": "http://2", "text": "text"}
    res = await create_or_update_documents(index, [doc3])
    assert res["successes"] == 1
    await _assert_n(index, 2)

    # cannot upload explicit id if identifiers are used
    doc4 = {"_id": "1", "url": "http://", "text": "text"}
    with pytest.raises(ValueError):
        await create_or_update_documents(index, [doc4])


@pytest.mark.anyio
async def test_invalid_adding_identifiers(index):
    # identifiers can only be added if (1) the index already uses identifiers or (2) the index is still empty (no docs)
    doc = {"text": "text"}
    await create_or_update_documents(index, [doc], fields={"text": "text"})
    await refresh_index(index)

    # adding an identifier to an existing index should fail
    doc = {"url": "http://", "text": "text"}
    with pytest.raises(ValueError):
        await create_or_update_documents(index, [doc], fields={"url": CreateDocumentField(type="keyword", identifier=True)})


@pytest.mark.anyio
async def test_valid_adding_identifiers(index):
    doc = {"text": "text"}
    await create_or_update_documents(index, [doc], fields={"text": CreateDocumentField(type="text", identifier=True)})

    # adding an additional identifier to an existing index should succeed if the index already has identifiers
    doc = {"url": "http://", "text": "text"}
    res = await create_or_update_documents(index, [doc], fields={"url": CreateDocumentField(type="keyword", identifier=True)})

    # the document should have been added because its not a full duplicate (in first doc url was empty)
    assert res["successes"] == 1
    await _assert_n(index, 2)

    # both the identifier for the first doc and the second doc should still work, so the following docs are
    # both duplicates
    doc1 = {"text": "text"}
    doc2 = {"url": "http://", "text": "text"}
    res = await create_or_update_documents(index, [doc1, doc2])
    assert res["successes"] == 2
    await _assert_n(index, 2)

    # the order of adding identifiers doesn't matter. a document having just the url uses only the url as identifier
    doc = {"url": "http://new"}
    res = await create_or_update_documents(index, [doc])
    assert res["successes"] == 1
    await _assert_n(index, 3)
    # second time its a duplicate
    res = await create_or_update_documents(index, [doc])
    assert res["successes"] == 1
    await _assert_n(index, 3)


async def _assert_n(index, n):
    await refresh_index(index)
    res = await query_documents(index)
    assert res is not None
    assert res.total_count == n
