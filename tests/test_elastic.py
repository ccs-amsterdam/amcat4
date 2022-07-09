from amcat4 import elastic
from amcat4.elastic import get_fields
from amcat4.index import Index
from amcat4.query import query_documents
from tests.conftest import upload


def test_upload_retrieve_document(index: Index):
    """Can we upload and retrieve documents"""
    a = dict(text="text", title="title", date="2021-03-09")
    ids = elastic.upload_documents(index.name, [a])
    assert [elastic._get_hash(a)], ids
    d = elastic.get_document(index.name, ids[0])
    assert d['title'] == a['title']
    # TODO: should a['date'] be a datetime?


def test_fields(index: Index):
    """Can we get the fields from an index"""
    fields = get_fields(index.name)
    assert set(fields.keys()) == {"title", "date", "text", "url"}
    assert fields['date']['type'] == "date"


def test_values(index: Index):
    """Can we get values for a specific field"""
    upload(index, [dict(bla=x) for x in ["odd", "even", "even"] * 10], columns={"bla": "keyword"})
    assert set(elastic.get_values(index.name, "bla")) == {"odd", "even"}


def test_update(index_docs):
    """Can we update a field on a document?"""
    assert elastic.get_document(index_docs.name, '0', _source=['annotations']) == {}
    elastic.update_document(index_docs.name, '0', {'annotations': {'x': 3}})
    assert elastic.get_document(index_docs.name, '0', _source=['annotations'])['annotations'] == {'x': 3}


def test_add_tag(index_docs):
    def q(*ids):
        return dict(query=dict(ids={"values": ids}))
    def tags():
        return {doc['_id']: doc['tag']
                for doc in query_documents(index_docs.name, fields=["tag"]).data
                if doc.get('tag')}
    assert tags() == {}
    elastic.update_tag_by_query(index_docs.name, "add",  q('0', '1'), "tag", "x")
    elastic.refresh(index_docs.name)
    assert tags() == {'0': ['x'], '1': ['x']}
    elastic.update_tag_by_query(index_docs.name, "add", q('1', '2'), "tag", "x")
    elastic.refresh(index_docs.name)
    assert tags() == {'0': ['x'], '1': ['x'], '2': ['x']}
    elastic.update_tag_by_query(index_docs.name, "add", q('2', '3'), "tag", "y")
    elastic.refresh(index_docs.name)
    assert tags() == {'0': ['x'], '1': ['x'], '2': ['x', 'y'], '3': ['y']}
    elastic.update_tag_by_query(index_docs.name, "remove", q('0', '2', '3'), "tag", "x")
    elastic.refresh(index_docs.name)
    assert tags() == {'1': ['x'], '2': ['y'], '3': ['y']}
