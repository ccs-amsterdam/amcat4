import string
from datetime import datetime
import time

from nose.tools import assert_equals

from amcat4.aggregate import query_aggregate
from tests.tools import upload, create_index, delete_index, with_index


_INDEX = 'amcat4_testaggregate__'


def _d(x):
    return datetime.strptime(x, "%Y-%m-%d")


def _y(y):
    return datetime(y, 1, 1).date()


def setup_module():
    create_index(_INDEX)
    upload([{'cat': 'a', 'subcat': 'x', 'i': 1, 'date': '2018-01-01', 'text': 'a text yo'},
            {'cat': 'a', 'subcat': 'x', 'i': 2, 'date': '2018-02-01', 'text': 'another text'},
            {'cat': 'a', 'subcat': 'y', 'i': 11, 'date': '2020-01-01', 'text': 'john doe'},
            {'cat': 'b', 'subcat': 'y', 'i': 31, 'date': '2018-01-01', 'text': 'john too has texts'},
            ], index_name=_INDEX, columns={'cat': 'keyword', 'subcat': 'keyword'})
    time.sleep(5)

def teardown_module():
    delete_index(_INDEX)


def q(*args, index=_INDEX, **kargs):
    def _key(x):
        if len(x) == 1:
            return x[0]
        return x
    result = query_aggregate(index, *args, **kargs)
    return {_key(vals[:-1]): vals[-1] for vals in result}


def test_aggregate():
    assert_equals(q("cat"), {"a": 3, "b": 1})
    assert_equals(q({"field": "date"}),
                  {_d('2018-01-01'): 2, _d('2018-02-01'): 1, _d('2020-01-01'): 1})


def test_aggregate_querystring():
    assert_equals(q("cat", queries=['john']), {"a": 1, "b": 1})
    assert_equals(q("cat", queries=['tex*']), {"a": 2, "b": 1})
    assert_equals(q("cat", queries=['yo', 'doe']), {"a": 2})


def test_interval():
    assert_equals(q({"field": "date", "interval": "year"}),
                  {_y(2018): 3, _y(2020): 1})
    assert_equals(q({"field": "i", "interval": "10"}),
                  {0.: 2, 10.: 1, 30.: 1})


def test_second_axis():
    assert_equals(q("cat", 'subcat'), {("a", "x"): 2, ("a", "y"): 1, ("b", "y"): 1})
    assert_equals(q({"field": "date", "interval": "year"}, 'cat'),
                  {(_y(2018), "a"): 2, (_y(2020), "a"): 1, (_y(2018), "b"): 1})
    assert_equals(q('cat', {"field": "date", "interval": "year"}),
                  {("a", _y(2018)): 2, ("a", _y(2020)): 1, ("b", _y(2018)): 1})


def test_filtered_aggregate():
    assert_equals(q('subcat', filters={'cat': {'value': 'a'}}), {"x": 2, "y": 1})


@with_index
def test_many_buckets(index_name):
    upload([{'cat': x} for x in string.ascii_letters*4], columns={'cat': 'keyword'})
    # time.sleep(5)
    assert_equals(q('cat', index=index_name), {x: 4 for x in string.ascii_letters})
