import functools
from datetime import datetime

from amcat4.aggregate import query_aggregate
from amcat4.index import Index


def do_query(index: Index, *args, **kargs):
    def _key(x):
        if len(x) == 1:
            return x[0]
        return x
    _axes, result = query_aggregate(index.name, *args, **kargs)
    return {_key(vals[:-1]): vals[-1] for vals in result}


def _d(x):
    return datetime.strptime(x, "%Y-%m-%d")


def _y(y):
    return datetime(y, 1, 1).date()


def test_aggregate(index_docs):
    q = functools.partial(do_query, index_docs)
    assert q("cat") == {"a": 3, "b": 1}
    assert q({"field": "date"}) == {_d('2018-01-01'): 2, _d('2018-02-01'): 1, _d('2020-01-01'): 1}


def test_aggregate_querystring(index_docs):
    q = functools.partial(do_query, index_docs)
    assert q("cat", queries=['toto']) == {"a": 1, "b": 1}
    assert q("cat", queries=['test*']) == {"a": 2, "b": 1}
    assert q("cat", queries=['"a text"', 'another']) == {"a": 2}


def test_interval(index_docs):
    q = functools.partial(do_query, index_docs)
    assert q({"field": "date", "interval": "year"}) == {_y(2018): 3, _y(2020): 1}
    assert q({"field": "i", "interval": "10"}) == {0.: 2, 10.: 1, 30.: 1}


def test_second_axis(index_docs):
    q = functools.partial(do_query, index_docs)
    assert q("cat", 'subcat') == {("a", "x"): 2, ("a", "y"): 1, ("b", "y"): 1}
    assert (q({"field": "date", "interval": "year"}, 'cat')
            == {(_y(2018), "a"): 2, (_y(2020), "a"): 1, (_y(2018), "b"): 1})
    assert (q('cat', {"field": "date", "interval": "year"})
            == {("a", _y(2018)): 2, ("a", _y(2020)): 1, ("b", _y(2018)): 1})
