import random
import string
from typing import Set, List

from nose.tools import assert_equal, assert_is_none

from amcat4.elastic import get_fields
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
    def q(*args, **kwargs) -> Set[int]:
        res = query.query_documents(project, *args, **kwargs)
        return {int(h['_id']) for h in res.data}

    texts = ["this is a text", "a test text", "and this is another test"]
    titles = ["titel", "titel", "bla"]
    upload([dict(title=title, date="2018-01-01", text=text) for (title, text) in zip(titles, texts)])
    assert_equal(q("test"), {1, 2})
    assert_equal(q('"a text"'), {0})

    assert_equal(q(filters={"title": {"value": "titel"}}),  {0, 1})
    assert_equal(q("this", filters={"title": {"value": "titel"}}),  {0})
    assert_equal(q("this"),  {0, 2})


@with_project
def test_range_query(project):
    def q(*args, **kwargs) -> Set[int]:
        res = query.query_documents(project, *args, **kwargs)
        return {int(h['_id']) for h in res.data}
    upload([dict(title="a title", date="2018-01-01"),
            dict(title="a second title", date="2019-01-01"),
            dict(title="title three", date="2020-01-01"),
            dict(title="more title", date="2021-01-01"),
            dict(title="last", date="2022-01-01")])

    assert_equal(q("title"), {0, 1, 2, 3})
    assert_equal(q(filters={"date": {"range": {"gt": "2020-01-01"}}}), {3, 4})
    assert_equal(q(filters={"date": {"range": {"gte": "2020-01-01"}}}), {2, 3, 4})
    assert_equal(q(filters={"date": {"range": {"gte": "2020-01-01", "lt": "2021-06-01"}}}), {2, 3})
    assert_equal(q("title", filters={"date": {"range": {"gt": "2020-01-01"}}}), {3})


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


@with_project
def test_scroll(project):
    upload([dict(text=x) for x in ["odd", "even"] * 10])
    r = query.query_documents(project, query_string="odd", scroll='5m', per_page=4)
    assert_equal(len(r.data), 4)
    assert_equal(r.total_count, 10)
    assert_equal(r.page_count, 3)
    all = list(r.data)

    r = query.query_documents(project, scroll_id=r.scroll_id)
    assert_equal(len(r.data), 4)
    all += r.data
    r = query.query_documents(project, scroll_id=r.scroll_id)
    assert_equal(len(r.data), 2)
    all += r.data
    r = query.query_documents(project, scroll_id=r.scroll_id)
    assert_is_none(r)
    assert_equal({int(h['_id']) for h in all}, {0, 2, 4, 6, 8, 10, 12, 14, 16, 18})


@with_project
def test_fields(project):
    assert_equal(get_fields(project), dict(title='text', date='date', text='text', url='keyword'))


@with_project
def test_values(project):
    upload([dict(bla=x) for x in ["odd", "even", "even"] * 10], columns={"bla": "keyword"})
    assert_equal(set(elastic.get_values(project, "bla")), {"odd", "even"})

