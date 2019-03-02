import random
import string

from nose.tools import assert_equal

from amcat4.elastic import get_fields
from tests.tools import with_index, upload

from amcat4 import elastic


def test_create_delete_list_index():
    name = 'amcat4_test_create_' + ''.join(random.choices(string.ascii_lowercase, k=32))
    try:
        assert name not in elastic._list_indices()
        elastic._create_index(name)
        assert name in elastic._list_indices()
        elastic._delete_index(name)
        assert name not in elastic._list_indices()
    finally:
        elastic._delete_index(name, ignore_missing=True)


@with_index
def test_upload_retrieve_document(index_name):
    a = dict(text="text", title="title", date="2018-01-01")
    ids = elastic.upload_documents(index_name, [a])
    assert_equal([elastic._get_hash(a)], ids)

    d = elastic.get_document(index_name, ids[0])
    assert_equal(d['title'], a['title'])
    # todo check date type




@with_index
def test_fields(index_name):
    assert_equal(get_fields(index_name), dict(title='text', date='date', text='text', url='keyword'))


@with_index
def test_values(index_name):
    upload([dict(bla=x) for x in ["odd", "even", "even"] * 10], columns={"bla": "keyword"})
    assert_equal(set(elastic.get_values(index_name, "bla")), {"odd", "even"})

