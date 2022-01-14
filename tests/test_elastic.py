from amcat4 import elastic
from amcat4.elastic import get_fields
from amcat4.index import Index
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
    assert get_fields(index.name) == dict(title='text', date='date', text='text', url='keyword')


def test_values(index: Index):
    """Can we get values for a specific field"""
    upload(index, [dict(bla=x) for x in ["odd", "even", "even"] * 10], columns={"bla": "keyword"})
    assert set(elastic.get_values(index.name, "bla")) == {"odd", "even"}


def test_update(index_docs):
    """Can we update a field on a document?"""
    assert elastic.get_document(index_docs.name, '0', _source=['annotations']) == {}
    elastic.update_document(index_docs.name, '0', {'annotations': {'x': 3}})
    assert elastic.get_document(index_docs.name, '0', _source=['annotations'])['annotations'] == {'x': 3}
