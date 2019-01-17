import random
import string
from typing import Set, List

from nose.tools import assert_equal
from tests.tools import with_project, upload

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


@with_project
def test_upload_retrieve_document(project):
    a = dict(text="text", title="title", date="2018-01-01")
    ids = elastic.upload_documents(project, [a])
    assert_equal([elastic._get_hash(a)], ids)

    d = elastic.get_document(project, ids[0])
    assert_equal(d['title'], a['title'])
    # todo check date type


@with_project
def test_query(project):
    def q(q) -> Set[int]:
        res = query.query_documents(project, q)
        return {int(h['_id']) for h in res.data}

    texts = ["this is a text", "a test text", "and another test"]
    upload([dict(title="title", date="2018-01-01", text=t) for t in texts])
    assert_equal(q("test"), {1, 2})
    assert_equal(q('"a text"'), {0})


@with_project
def test_pagination(project):
    upload([dict(title=str(i), date="2018-01-01", text="text") for i in range(95)])
    x = query.query_documents(project, per_page=30)
    assert_equal(x.page_count, 4)
    assert_equal(x.per_page, 30)
    assert_equal(len(x.data), 30)
    assert_equal(x.page, 0)
    x = query.query_documents(project, per_page=30, page=3)
    assert_equal(x.page_count, 4)
    assert_equal(x.per_page, 30)
    assert_equal(len(x.data), 95 - 3*30)
    assert_equal(x.page, 3)


@with_project
def test_sort(project):
    def q(key) -> List[int]:
        res = query.query_documents(project, per_page=5, sort=key)
        return [int(h['_id']) for h in res.data]
    upload([dict(title=str(i), date="2018-01-01", text="text", id=i, pagenr=abs(50-i)) for i in range(100)])
    assert_equal(q('id'), [0, 1, 2, 3, 4])
    assert_equal(q('pagenr,id'), [50, 49, 51, 48, 52])
    assert_equal(q('pagenr:desc,id'), [0, 1, 99, 2, 98])

