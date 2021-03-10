from typing import Iterable, List
import time

from nose.tools import assert_equal, assert_is_none

from amcat4 import query
from tests.tools import create_index, upload, delete_index, _TEST_INDEX


def setup_module():
    create_index()
    upload([dict(id=i, pagenr=abs(10-i), text=text) for (i, text) in enumerate(["odd", "even"]*10)])
    # time.sleep(5)


def teardown_module():
    delete_index()


def q(key, per_page=5, *args, **kwargs) -> List[int]:
    res = query.query_documents(_TEST_INDEX, per_page=per_page, sort=key, *args, **kwargs)
    return [int(h['_id']) for h in res.data]


def test_pagination():
    x = query.query_documents(_TEST_INDEX, per_page=6)
    assert_equal(x.page_count, 4)
    assert_equal(x.per_page, 6)
    assert_equal(len(x.data), 6)
    assert_equal(x.page, 0)
    x = query.query_documents(_TEST_INDEX, per_page=6, page=3)
    assert_equal(x.page_count, 4)
    assert_equal(x.per_page, 6)
    assert_equal(len(x.data), 20 - 3*6)
    assert_equal(x.page, 3)


def test_sort():
    assert_equal(q('id'), [0, 1, 2, 3, 4])
    assert_equal(q('pagenr,id'), [10, 9, 11, 8, 12])
    assert_equal(q('pagenr:desc,id'), [0, 1, 19, 2, 18])


def test_scroll():
    r = query.query_documents(_TEST_INDEX, queries=["odd"], scroll='5m', per_page=4)
    assert_equal(len(r.data), 4)
    assert_equal(r.total_count.get("value"), 10)
    assert_equal(r.page_count, 3)
    allids = list(r.data)

    r = query.query_documents(_TEST_INDEX, scroll_id=r.scroll_id)
    assert_equal(len(r.data), 4)
    allids += r.data
    r = query.query_documents(_TEST_INDEX, scroll_id=r.scroll_id)
    assert_equal(len(r.data), 2)
    allids += r.data
    r = query.query_documents(_TEST_INDEX, scroll_id=r.scroll_id)
    assert_is_none(r)
    assert_equal({int(h['_id']) for h in allids}, {0, 2, 4, 6, 8, 10, 12, 14, 16, 18})
