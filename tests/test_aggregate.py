from datetime import datetime

from nose.tools import assert_equals

from amcat4.aggregate import query_aggregate
from tests.tools import upload, create_index, delete_index, _TEST_INDEX


def _d(x):
    return datetime.strptime(x, "%Y-%m-%d")


def _y(y):
    return datetime(y, 1, 1)


def setup_module():
    create_index()
    upload([{'cat': 'a', 'subcat': 'x', 'i': 1, 'date': '2018-01-01'},
            {'cat': 'a', 'subcat': 'x', 'i': 2, 'date': '2018-02-01'},
            {'cat': 'a', 'subcat': 'y', 'i': 11, 'date': '2020-01-01'},
            {'cat': 'b', 'subcat': 'y', 'i': 31, 'date': '2018-01-01'},
            ], columns={'cat': 'keyword', 'subcat': 'keyword'})


def teardown_module():
    delete_index()


def q(*args, **kargs):
    result = query_aggregate(_TEST_INDEX, *args, **kargs)
    def _key(x):
        if len(x) == 1:
            return x[0]
        return x
    return {_key(vals[:-1]): vals[-1] for vals in result}


def test_aggregate():
    assert_equals(q("cat"), {"a": 3, "b": 1})

    assert_equals(q({"field": "date"}),
                  {_d('2018-01-01'): 2, _d('2018-02-01'): 1, _d('2020-01-01'): 1})


def test_interval():
    assert_equals(q({"field": "date", "interval": "year"}),
                  {_y(2018): 3, _y(2020): 1, _y(2019): 0})
    assert_equals(q({"field": "i", "interval": "10"}),
                  {0.: 2, 10.: 1, 20.: 0, 30.: 1})


def test_second_axis():
    assert_equals(q("cat", 'subcat'), {("a", "x"): 2, ("a", "y"): 1, ("b", "y"): 1})
    assert_equals(q({"field": "date", "interval": "year"}, 'cat'),
                  {(_y(2018), "a"): 2, (_y(2020), "a"): 1, (_y(2018), "b"): 1})
    assert_equals(q('cat', {"field": "date", "interval": "year"}),
                  {("a", _y(2018)): 2, ("a", _y(2019)): 0, ("a", _y(2020)): 1, ("b", _y(2018)): 1})
