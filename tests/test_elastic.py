from datetime import datetime

import pytest

from amcat4.projects.documents import (
    delete_documents_by_query,
    get_document,
    update_document,
    update_document_tag_by_query,
    update_documents_by_query,
    upload_documents,
)
from amcat4.projects.index import refresh_index
from amcat4.systemdata.fields import create_fields, field_values, list_fields
from amcat4.models import CreateField, FieldSpec, IndexId
from amcat4.projects.query import query_documents
from tests.conftest import upload


def test_upload_retrieve_document(index):
    """Can we upload and retrieve documents"""
    a = dict(
        text="text",
        title="title",
        date="2021-03-09",
        _id="test",
        term_tfidf=[{"term": "test", "value": 0.2}, {"term": "value", "value": 0.3}],
    )
    test = upload_documents(index, [a], fields={"text": "text", "title": "text", "date": "date", "term_tfidf": "object"})
    print(test)
    refresh_index(index)
    print(query_documents(index).data)
    d = get_document(index, "test")
    assert d["title"] == a["title"]
    assert d["term_tfidf"] == a["term_tfidf"]
    # TODO: should a['date'] be a datetime?


def test_data_coerced(index):
    """Are field values coerced to the correct field type"""
    create_fields(index, {"i": "integer", "x": "number", "title": "text", "date": "date", "text": "text"})
    a = dict(_id="DoccyMcDocface", text="text", title="test-numeric", date="2022-12-13", i="1", x="1.1")
    upload_documents(index, [a])
    d = get_document(index, "DoccyMcDocface")
    assert isinstance(d["i"], int)
    a = dict(text="text", title=1, date="2022-12-13")
    upload_documents(index, [a])
    d = get_document(index, "DoccyMcDocface")
    assert isinstance(d["title"], str)


def test_fields(index):
    """Can we get the fields from an index"""
    create_fields(index, {"title": "text", "date": "date", "text": "text", "url": "keyword"})
    fields = list_fields(index)
    assert set(fields.keys()) == {"title", "date", "text", "url"}
    assert fields["title"].type == "text"
    assert fields["date"].type == "date"

    # default settings
    assert fields["date"].identifier is False
    assert fields["date"].client_settings is not None

    # default settings depend on the type
    assert fields["date"].metareader.access == "read"
    assert fields["text"].metareader.access == "none"


def test_values(index):
    """Can we get values for a specific field"""
    upload(index, [dict(bla=x) for x in ["odd", "even", "even"] * 10], fields={"bla": "keyword"})
    assert set(field_values(index, "bla", 10)) == {"odd", "even"}


def test_update(index_docs):
    """Can we update a field on a document?"""
    create_fields(index_docs, {"annotations": "object"})
    assert get_document(index_docs, "0", _source=["annotations"]) == {}
    update_document(index_docs, "0", {"annotations": {"x": 3}})
    assert get_document(index_docs, "0", _source=["annotations"])["annotations"] == {"x": 3}


def test_update_by_query(index_docs):
    def cats():
        res = query_documents(index_docs, fields=[FieldSpec(name="cat"), FieldSpec(name="subcat")])
        return {doc["_id"]: doc.get("subcat") for doc in (res.data if res else [])}

    assert cats() == {"0": "x", "1": "x", "2": "y", "3": "y"}
    update_documents_by_query(index_docs, query=dict(term={"cat": dict(value="a")}), field="subcat", value="z")
    assert cats() == {"0": "z", "1": "z", "2": "z", "3": "y"}
    update_documents_by_query(index_docs, query=dict(term={"cat": dict(value="b")}), field="subcat", value=None)
    assert cats() == {"0": "z", "1": "z", "2": "z", "3": None}
    assert "subcat" not in get_document(index_docs, "3").keys()


def test_delete_by_query(index_docs):
    def ids():
        refresh_index(index_docs)
        res = query_documents(index_docs)
        return {doc["_id"] for doc in (res.data if res else [])}

    assert ids() == {"0", "1", "2", "3"}
    delete_documents_by_query(index_docs, query=dict(term={"cat": dict(value="a")}))
    assert ids() == {"3"}


def test_add_tag(index_docs):
    def q(*ids):
        return dict(query=dict(ids={"values": ids}))

    def tags():
        res = query_documents(index_docs, fields=[FieldSpec(name="tag")])
        return {doc["_id"]: doc["tag"] for doc in (res.data if res else []) if "tag" in doc and doc["tag"] is not None}

    assert tags() == {}
    update_document_tag_by_query(index_docs, "add", q("0", "1"), "tag", "x")
    refresh_index(index_docs)
    assert tags() == {"0": ["x"], "1": ["x"]}
    update_document_tag_by_query(index_docs, "add", q("1", "2"), "tag", "x")
    refresh_index(index_docs)
    assert tags() == {"0": ["x"], "1": ["x"], "2": ["x"]}
    update_document_tag_by_query(index_docs, "add", q("2", "3"), "tag", "y")
    refresh_index(index_docs)
    assert tags() == {"0": ["x"], "1": ["x"], "2": ["x", "y"], "3": ["y"]}
    update_document_tag_by_query(index_docs, "remove", q("0", "2", "3"), "tag", "x")
    refresh_index(index_docs)
    assert tags() == {"1": ["x"], "2": ["y"], "3": ["y"]}


def test_upload_without_identifiers(index):
    doc = {"title": "titel", "text": "text", "date": datetime(2020, 1, 1)}
    res = upload_documents(index, [doc], fields={"title": "text", "text": "text", "date": "date"})
    assert res["successes"] == 1
    _assert_n(index, 1)

    # this doesnt identify duplicates
    res = upload_documents(index, [doc])
    assert res["successes"] == 1
    _assert_n(index, 2)


def test_upload_with_explicit_ids(index):
    doc = {"_id": "1", "title": "titel", "text": "text", "date": datetime(2020, 1, 1)}
    res = upload_documents(index, [doc], fields={"title": "text", "text": "text", "date": "date"})
    assert res["successes"] == 1
    assert get_document(index, "1")["text"] == "text"

    # uploading a doc with same id should replace the existing document
    doc = {"_id": "1", "title": "new title", "date": datetime(2020, 1, 1)}
    res = upload_documents(index, [doc])
    assert res["successes"] == 1
    _assert_n(index, 1)
    assert get_document(index, "1")["title"] == "new title"


def test_upload_with_identifiers(index):
    doc = {"url": "http://", "text": "text"}
    res = upload_documents(index, [doc], fields={"url": CreateField(type="keyword", identifier=True), "text": "text"})
    assert res["successes"] == 1
    _assert_n(index, 1)

    # Re-uploading a document with the same identifier should update the document
    doc2 = {"url": "http://", "text": "text2"}
    res = upload_documents(index, [doc2])
    assert res["successes"] == 1
    _assert_n(index, 1)
    res = query_documents(index, fields=[FieldSpec(name="text")])
    assert {doc["text"] for doc in (res.data if res else [])} == {"text2"}

    doc3 = {"url": "http://2", "text": "text"}
    res = upload_documents(index, [doc3])
    assert res["successes"] == 1
    _assert_n(index, 2)

    # cannot upload explicit id if identifiers are used
    doc4 = {"_id": "1", "url": "http://", "text": "text"}
    with pytest.raises(ValueError):
        upload_documents(index, [doc4])


def test_invalid_adding_identifiers(index):
    # identifiers can only be added if (1) the index already uses identifiers or (2) the index is still empty (no docs)
    doc = {"text": "text"}
    upload_documents(index, [doc], fields={"text": "text"})
    refresh_index(index)

    # adding an identifier to an existing index should fail
    doc = {"url": "http://", "text": "text"}
    with pytest.raises(ValueError):
        upload_documents(index, [doc], fields={"url": CreateField(type="keyword", identifier=True)})


def test_valid_adding_identifiers(index):
    doc = {"text": "text"}
    upload_documents(index, [doc], fields={"text": CreateField(type="text", identifier=True)})

    # adding an additional identifier to an existing index should succeed if the index already has identifiers
    doc = {"url": "http://", "text": "text"}
    res = upload_documents(index, [doc], fields={"url": CreateField(type="keyword", identifier=True)})

    # the document should have been added because its not a full duplicate (in first doc url was empty)
    assert res["successes"] == 1
    _assert_n(index, 2)

    # both the identifier for the first doc and the second doc should still work, so the following docs are
    # both duplicates
    doc1 = {"text": "text"}
    doc2 = {"url": "http://", "text": "text"}
    res = upload_documents(index, [doc1, doc2])
    assert res["successes"] == 2
    _assert_n(index, 2)

    # the order of adding identifiers doesn't matter. a document having just the url uses only the url as identifier
    doc = {"url": "http://new"}
    res = upload_documents(index, [doc])
    assert res["successes"] == 1
    _assert_n(index, 3)
    # second time its a duplicate
    res = upload_documents(index, [doc])
    assert res["successes"] == 1
    _assert_n(index, 3)


def _assert_n(index, n):
    refresh_index(index)
    res = query_documents(index)
    assert res is not None
    assert res.total_count == n
