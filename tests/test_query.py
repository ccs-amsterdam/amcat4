from typing import Set
import time

from nose.tools import assert_equal

from amcat4 import query
from tests.tools import create_index, upload, delete_index, _TEST_INDEX


_TEST_DOCUMENTS = [
    {'cat': 'a', 'subcat': 'x', 'i': 1, 'date': '2018-01-01', 'text': 'this is a text', },
    {'cat': 'a', 'subcat': 'x', 'i': 2, 'date': '2018-02-01', 'text': 'a test text', },
    {'cat': 'a', 'subcat': 'y', 'i': 11, 'date': '2020-01-01', 'text': 'and this is another test', 'title': 'bla'},
    {'cat': 'b', 'subcat': 'y', 'i': 31, 'date': '2018-01-01', 'text': 'Toto je testovací článek', 'title': 'more bla'},
]


def setup_module():
    create_index()
    upload(_TEST_DOCUMENTS, columns={'cat': 'keyword', 'subcat': 'keyword', 'i': 'int'})

def teardown_module():
    delete_index()


def q(q=None, **kwargs) -> Set[int]:
    if q is not None:
        kwargs['queries'] = [q]
    res = query.query_documents(_TEST_INDEX, **kwargs)
    return {int(h['_id']) for h in res.data}


def test_query():
    assert_equal(q("test"), {1, 2})
    assert_equal(q("test*"), {1, 2, 3})
    assert_equal(q('"a text"'), {0})

    assert_equal(q(queries=["this", "toto"]), {0, 2, 3})

    assert_equal(q(filters={"title": {"value": "title"}}),  {0, 1})
    assert_equal(q("this", filters={"title": {"value": "title"}}),  {0})
    assert_equal(q("this"),  {0, 2})


def test_range_query():
    assert_equal(q(filters={"date": {"range": {"gt": "2018-02-01"}}}), {2})
    assert_equal(q(filters={"date": {"range": {"gte": "2018-02-01"}}}), {1, 2})
    assert_equal(q(filters={"date": {"range": {"gte": "2018-02-01", "lt": "2020-01-01"}}}), {1})
    assert_equal(q("title", filters={"date": {"range": {"gt": "2018-01-01"}}}), {1})


def test_fields():
    res = query.query_documents(_TEST_INDEX, queries=["test"], fields=["cat", "title"])
    assert_equal(set(res.data[0].keys()), {"cat", "title", "_id"})
