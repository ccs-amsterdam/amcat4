import random
import string
from typing import Set, List

from nose.tools import assert_equal

from amcat4 import elastic, query


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


def upload_clean(docs):
    """
    Setup a clean database with these docs (which get an incremental _id)
    """
    elastic.delete_project(_TEST_PROJECT, ignore_missing=True)
    elastic.create_project(_TEST_PROJECT)
    for i, doc in enumerate(docs):
        doc['_id'] = str(i)
    elastic.upload_documents(_TEST_PROJECT, docs)
    elastic.flush()


def test_upload_retrieve_document():
    a = dict(text="text", title="title", date="2018-01-01")
    ids = elastic.upload_documents(_TEST_PROJECT, [a])
    assert_equal([elastic._get_hash(a)], ids)

    d = elastic.get_document(_TEST_PROJECT, ids[0])
    assert_equal(d['title'], a['title'])
    # todo check date type


def test_query():
    def q(q) -> Set[int]:
        res = query.query_documents(_TEST_PROJECT, q)
        return {int(h['_id']) for h in res.data}

    texts = ["this is a text", "a test text", "and another test"]
    upload_clean([dict(_id=str(id), title="title", date="2018-01-01", text=t) for t in texts])
    assert_equal(q("test"), {1, 2})
    assert_equal(q('"a text"'), {0})


def test_pagination():
    upload_clean([dict(title=str(i), date="2018-01-01", text="text") for i in range(95)])
    x = query.query_documents(_TEST_PROJECT, per_page=30)
    assert_equal(x.page_count, 4)
    assert_equal(x.per_page, 30)
    assert_equal(len(x.data), 30)
    assert_equal(x.page, 1)
    x = query.query_documents(_TEST_PROJECT, per_page=30, page=4)
    assert_equal(x.page_count, 4)
    assert_equal(x.per_page, 30)
    assert_equal(len(x.data), 95 - 3*30)
    assert_equal(x.page, 4)


def test_sort():
    def q(key) -> List[int]:
        res = query.query_documents(_TEST_PROJECT, per_page=5, sort=key)
        return [int(h['_id']) for h in res.data]
    upload_clean([dict(title=str(i), date="2018-01-01", text="text", id=i, pagenr=abs(50-i)) for i in range(100)])
    assert_equal(q('id'), [0, 1, 2, 3, 4])
    assert_equal(q('pagenr,id'), [50, 49, 51, 48, 52])
    assert_equal(q('pagenr:desc,id'), [0, 1, 99, 2, 98])

