import functools
from datetime import datetime, date

from amcat4.aggregate import query_aggregate, Axis, Aggregation
from amcat4.api.query import _standardize_queries
from amcat4.models import CreateField
from tests.conftest import upload
from tests.tools import dictset


def do_query(index: str, *args, **kwargs):
    def _key(x):
        if len(x) == 1:
            return x[0]
        return x

    axes = [Axis(x) if isinstance(x, str) else x for x in args]

    result = query_aggregate(index, axes, **kwargs)
    return {_key(vals[:-1]): vals[-1] for vals in result.data}


def _d(x):
    return datetime.strptime(x, "%Y-%m-%d")


def _y(y):
    return datetime(y, 1, 1).date()


def test_aggregate(index_docs):
    q = functools.partial(do_query, index_docs)
    assert q(Axis("cat")) == {"a": 3, "b": 1}
    assert q(Axis(field="date")) == {_d("2018-01-01"): 2, _d("2018-02-01"): 1, _d("2020-01-01"): 1}


def test_aggregate_querystring(index_docs):
    q = functools.partial(do_query, index_docs)
    assert q("cat", queries=_standardize_queries(["toto"])) == {"a": 1, "b": 1}
    assert q("cat", queries=_standardize_queries(["test*"])) == {"a": 2, "b": 1}
    assert q("cat", queries=_standardize_queries(['"a text"', "another"])) == {"a": 2}


def test_interval(index_docs):
    q = functools.partial(do_query, index_docs)
    assert q(Axis(field="date", interval="year")) == {_y(2018): 3, _y(2020): 1}
    assert q(Axis(field="i", interval="10")) == {0.0: 2, 10.0: 1, 30.0: 1}


def test_second_axis(index_docs):
    q = functools.partial(do_query, index_docs)
    assert q("cat", "subcat") == {("a", "x"): 2, ("a", "y"): 1, ("b", "y"): 1}
    assert q(Axis(field="date", interval="year"), "cat") == {(_y(2018), "a"): 2, (_y(2020), "a"): 1, (_y(2018), "b"): 1}
    assert q("cat", Axis(field="date", interval="year")) == {("a", _y(2018)): 2, ("a", _y(2020)): 1, ("b", _y(2018)): 1}


def test_count(index_docs):
    """Does aggregation without axes work"""
    assert do_query(index_docs) == {(): 4}
    assert do_query(index_docs, queries={"text": "text"}) == {(): 2}


def test_byquery(index_docs):
    """Get number of documents per query"""
    assert do_query(index_docs, Axis("_query"), queries={"text": "text", "test*": "test*"}) == {"text": 2, "test*": 3}
    assert do_query(index_docs, Axis("_query"), Axis("subcat"), queries={"text": "text", "test*": "test*"}) == {
        ("text", "x"): 2,
        ("test*", "x"): 1,
        ("test*", "y"): 2,
    }
    assert do_query(index_docs, Axis("subcat"), Axis("_query"), queries={"text": "text", "test*": "test*"}) == {
        ("x", "text"): 2,
        ("x", "test*"): 1,
        ("y", "test*"): 2,
    }


def test_metric(index_docs: str):
    """Do metric aggregations (e.g. avg(x)) work?"""

    # Single and double aggregation with axis
    def q(axes, aggregations):
        return dictset(query_aggregate(index_docs, axes, aggregations).as_dicts())

    assert q([Axis("subcat")], [Aggregation("i", "avg")]) == dictset(
        [{"subcat": "x", "n": 2, "avg_i": 1.5}, {"subcat": "y", "n": 2, "avg_i": 21.0}]
    )
    assert q([Axis("subcat")], [Aggregation("i", "avg"), Aggregation("i", "max")]) == dictset(
        [{"subcat": "x", "n": 2, "avg_i": 1.5, "max_i": 2.0}, {"subcat": "y", "n": 2, "avg_i": 21.0, "max_i": 31.0}]
    )
    # Aggregation only
    assert q(None, [Aggregation("i", "avg")]) == dictset([{"n": 4, "avg_i": 11.25}])
    assert q(None, [Aggregation("i", "avg"), Aggregation("i", "max")]) == dictset([{"n": 4, "avg_i": 11.25, "max_i": 31.0}])

    # Count only
    assert q([], []) == dictset([{"n": 4}])

    # Check value handling - Aggregation on date fields
    assert q(None, [Aggregation("date", "max")]) == dictset([{"n": 4, "max_date": "2020-01-01T00:00:00"}])
    assert q([Axis("subcat")], [Aggregation("date", "avg")]) == dictset(
        [
            {"subcat": "x", "n": 2, "avg_date": "2018-01-16T12:00:00"},
            {"subcat": "y", "n": 2, "avg_date": "2019-01-01T00:00:00"},
        ]
    )


def test_aggregate_datefunctions(index: str):
    q = functools.partial(do_query, index)
    docs = [
        dict(date=x)
        for x in [
            "2018-01-01T04:00:00",  # monday night
            "2018-01-01T09:00:00",  # monday morning
            "2018-01-11T09:00:00",  # thursday morning
            "2018-01-17T11:00:00",  # wednesday morning
            "2018-01-17T18:00:00",  # wednesday evening
            "2018-03-07T23:59:00",  # wednesday evening
        ]
    ]
    upload(index, docs, fields=dict(date=CreateField(type="date")))
    assert q(Axis("date", interval="day")) == {
        date(2018, 1, 1): 2,
        date(2018, 1, 11): 1,
        date(2018, 1, 17): 2,
        date(2018, 3, 7): 1,
    }
    assert q(Axis("date", interval="dayofweek")) == {"Monday": 2, "Wednesday": 3, "Thursday": 1}
    assert q(Axis("date", interval="daypart")) == {"Night": 1, "Morning": 3, "Evening": 2}
    assert q(Axis("date", interval="monthnr")) == {1: 5, 3: 1}
    assert q(Axis("date", interval="yearnr")) == {2018: 6}
    assert q(Axis("date", interval="dayofmonth")) == {1: 2, 11: 1, 17: 2, 7: 1}
    assert q(Axis("date", interval="weeknr")) == {1: 2, 2: 1, 3: 2, 10: 1}
    assert q(Axis("date", interval="month"), Axis("date", interval="dayofmonth")) == {
        (date(2018, 1, 1), 1): 2,
        (date(2018, 1, 1), 11): 1,
        (date(2018, 1, 1), 17): 2,
        (date(2018, 3, 1), 7): 1,
    }
