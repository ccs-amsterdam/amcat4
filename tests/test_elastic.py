from datetime import datetime

from amcat4.index import (
    refresh_index,
    upload_documents,
    get_document,
    update_document,
    update_tag_by_query,
)
from amcat4.fields import update_fields, get_fields, get_field_values
from amcat4.query import query_documents
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
    upload_documents(index, [a])
    d = get_document(index, "test")
    assert d["title"] == a["title"]
    assert d["term_tfidf"] == a["term_tfidf"]
    # TODO: should a['date'] be a datetime?


def test_data_coerced(index):
    """Are field values coerced to the correct field type"""
    update_fields(index, {"i": "long"})
    a = dict(_id="DoccyMcDocface", text="text", title="test-numeric", date="2022-12-13", i="1")
    upload_documents(index, [a])
    d = get_document(index, "DoccyMcDocface")
    assert isinstance(d["i"], float)
    a = dict(text="text", title=1, date="2022-12-13")
    upload_documents(index, [a])
    d = get_document(index, "DoccyMcDocface")
    assert isinstance(d["title"], str)


def test_fields(index):
    """Can we get the fields from an index"""
    fields = get_fields(index)
    assert set(fields.keys()) == {"title", "date", "text", "url"}
    assert fields["date"]["type"] == "date"


def test_values(index):
    """Can we get values for a specific field"""
    upload(index, [dict(bla=x) for x in ["odd", "even", "even"] * 10], fields={"bla": "keyword"})
    assert set(get_field_values(index, "bla", 10)) == {"odd", "even"}


def test_update(index_docs):
    """Can we update a field on a document?"""
    assert get_document(index_docs, "0", _source=["annotations"]) == {}
    update_document(index_docs, "0", {"annotations": {"x": 3}})
    assert get_document(index_docs, "0", _source=["annotations"])["annotations"] == {"x": 3}


def test_add_tag(index_docs):
    def q(*ids):
        return dict(query=dict(ids={"values": ids}))

    def tags():
        return {
            doc["_id"]: doc["tag"]
            for doc in query_documents(index_docs, fields=["tag"]).data
            if "tag" in doc and doc["tag"] is not None
        }

    assert tags() == {}
    update_tag_by_query(index_docs, "add", q("0", "1"), "tag", "x")
    refresh_index(index_docs)
    assert tags() == {"0": ["x"], "1": ["x"]}
    update_tag_by_query(index_docs, "add", q("1", "2"), "tag", "x")
    refresh_index(index_docs)
    assert tags() == {"0": ["x"], "1": ["x"], "2": ["x"]}
    update_tag_by_query(index_docs, "add", q("2", "3"), "tag", "y")
    refresh_index(index_docs)
    assert tags() == {"0": ["x"], "1": ["x"], "2": ["x", "y"], "3": ["y"]}
    update_tag_by_query(index_docs, "remove", q("0", "2", "3"), "tag", "x")
    refresh_index(index_docs)
    assert tags() == {"1": ["x"], "2": ["y"], "3": ["y"]}


def test_deduplication(index):
    doc = {"title": "titel", "text": "text", "date": datetime(2020, 1, 1)}
    upload_documents(index, [doc])
    refresh_index(index)
    assert query_documents(index).total_count == 1
    upload_documents(index, [doc])
    refresh_index(index)
    assert query_documents(index).total_count == 1
