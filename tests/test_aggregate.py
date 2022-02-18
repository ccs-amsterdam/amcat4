import functools
from datetime import datetime

from amcat4.aggregate import query_aggregate, Axis
from amcat4.index import Index


def do_query(index: Index, *axes, **kargs):
    def _key(x):
        if len(x) == 1:
            return x[0]
        return x
    axes = [Axis(x) if isinstance(x, str) else x for x in axes]
    result = query_aggregate(index.name, axes, **kargs)
    return {_key(vals[:-1]): vals[-1] for vals in result.data}


def _d(x):
    return datetime.strptime(x, "%Y-%m-%d")


def _y(y):
    return datetime(y, 1, 1).date()


def test_aggregate(index_docs):
    q = functools.partial(do_query, index_docs)
    assert q(Axis("cat")) == {"a": 3, "b": 1}
    assert q(Axis(field="date")) == {_d('2018-01-01'): 2, _d('2018-02-01'): 1, _d('2020-01-01'): 1}


def test_aggregate_querystring(index_docs):
    q = functools.partial(do_query, index_docs)
    assert q("cat", queries=['toto']) == {"a": 1, "b": 1}
    assert q("cat", queries=['test*']) == {"a": 2, "b": 1}
    assert q("cat", queries=['"a text"', 'another']) == {"a": 2}


def test_interval(index_docs):
    q = functools.partial(do_query, index_docs)
    assert q(Axis(field="date", interval="year")) == {_y(2018): 3, _y(2020): 1}
    assert q(Axis(field="i", interval="10")) == {0.: 2, 10.: 1, 30.: 1}


def test_second_axis(index_docs):
    q = functools.partial(do_query, index_docs)
    assert q("cat", 'subcat') == {("a", "x"): 2, ("a", "y"): 1, ("b", "y"): 1}
    assert (q(Axis(field="date", interval="year"), 'cat')
            == {(_y(2018), "a"): 2, (_y(2020), "a"): 1, (_y(2018), "b"): 1})
    assert (q('cat', Axis(field="date", interval="year"))
            == {("a", _y(2018)): 2, ("a", _y(2020)): 1, ("b", _y(2018)): 1})



def test_count(index_docs):
    """Does aggregation without axes work"""
    assert do_query(index_docs) == {(): 4}
    assert do_query(index_docs, queries=["text"]) == {(): 2}


def test_byquery(index_docs):
    """Get number of documents per query"""
    assert do_query(index_docs, Axis("_query"), queries=["text", "test*"]) == {"text": 2, "test*": 3}
    assert (do_query(index_docs, Axis("_query"), Axis("subcat"), queries=["text", "test*"]) ==
            {("text", "x"): 2, ("test*", "x"): 1, ("test*", "y"): 2})


TEST_DOCUMENTS = [
    {'cat': 'a', 'subcat': 'x', 'i': 1, 'date': '2018-01-01', 'text': 'this is a text', },
    {'cat': 'a', 'subcat': 'x', 'i': 2, 'date': '2018-02-01', 'text': 'a test text', },
    {'cat': 'a', 'subcat': 'y', 'i': 11, 'date': '2020-01-01', 'text': 'and this is another test toto', 'title': 'bla'},
    {'cat': 'b', 'subcat': 'y', 'i': 31, 'date': '2018-01-01', 'text': 'Toto je testovací článek', 'title': 'more bla'},
]


def test_metric(index_docs):
    """Do metric aggregations (e.g. avg(x)) work?"""
    import json
    sj = lambda dicts: set(json.dumps(d) for d in dicts)
    assert (sj(query_aggregate(index_docs.name, [Axis("subcat")],
                                aggregations={"avg_i": {"avg": {"field": "i"}}}).as_dicts()) ==
            sj([{"subcat": "x", "n": 2, "avg_i": 1.5},
             {"subcat": "y", "n": 2, "avg_i": 21.0}]))
    #assert do_query(index_docs, Axis("subcat")) is None
