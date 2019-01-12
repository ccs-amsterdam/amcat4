import random
import string

from nose.tools import assert_equal

from amcat4 import elastic


def test_create_delete_list_project():
    name = '__test__create_' + ''.join(random.choices(string.ascii_lowercase, k=32))
    try:
        assert name not in elastic.list_projects()
        elastic.create_project(name)
        assert name in elastic.list_projects()
        elastic.delete_project(name)
        assert name not in elastic.list_projects()
    finally:
        elastic.delete_project(name, ignore_missing=True)


_TEST_PROJECT = '__test__' + ''.join(random.choices(string.ascii_lowercase, k=32))


def setup_module():
    elastic.create_project(_TEST_PROJECT)


def teardown_module():
    elastic.delete_project(_TEST_PROJECT, ignore_missing=True)


def test_upload_retrieve_document():
    a = dict(text="text", title="title", date="2018-01-01")
    ids = elastic.upload_documents(_TEST_PROJECT, [a])
    assert_equal([elastic._get_hash(a)], ids)

    d = elastic.get_document(_TEST_PROJECT, ids[0])
    assert_equal(d['title'], a['title'])
    # todo check date type


def test_query():
    texts = ["this is a text", "a test text", "and another test"]
    docs = [dict(title="title", date="2018-01-01", text=t) for t in texts]
    id0, id1, id2 = elastic.upload_documents(_TEST_PROJECT, docs)
    elastic.flush()
    r = [h['_id'] for h in elastic.query_documents(_TEST_PROJECT, "test")]
    assert_equal(set(r), {id1, id2})

    r = [h['_id'] for h in elastic.query_documents(_TEST_PROJECT, '"a text"')]
    assert_equal(set(r), {id0})
