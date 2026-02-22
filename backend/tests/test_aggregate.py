import functools
from datetime import date, datetime, timezone

import pytest

from amcat4.api.index_query import _standardize_queries
from amcat4.models import CreateDocumentField
from amcat4.projects.aggregate import Aggregation, Axis, query_aggregate
from tests.conftest import upload
from tests.tools import dictset


async def do_query(index: str, *args, **kwargs):
    def _key(x):
        if len(x) == 1:
            return x[0]
        return x

    axes = [Axis(x) if isinstance(x, str) else x for x in args]

    result = await query_aggregate(index, axes, **kwargs)
    return {_key(vals[:-1]): vals[-1] for vals in result.data}


def _d(x):
    return datetime.strptime(x, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _y(y):
    return datetime(y, 1, 1).date()


@pytest.mark.anyio
async def test_aggregate(index_docs):
    q = functools.partial(do_query, index_docs)
    assert await q(Axis("cat")) == {"a": 3, "b": 1}
    assert await q(Axis(field="date")) == {_d("2018-01-01"): 2, _d("2018-02-01"): 1, _d("2020-01-01"): 1}


@pytest.mark.anyio
async def test_aggregate_querystring(index_docs):
    q = functools.partial(do_query, index_docs)
    assert await q("cat", queries=_standardize_queries(["toto"])) == {"a": 1, "b": 1}
    assert await q("cat", queries=_standardize_queries(["test*"])) == {"a": 2, "b": 1}
    assert await q("cat", queries=_standardize_queries(['"a text"', "another"])) == {"a": 2}


@pytest.mark.anyio
async def test_interval(index_docs):
    q = functools.partial(do_query, index_docs)
    assert await q(Axis(field="date", interval="year")) == {_y(2018): 3, _y(2020): 1}
    assert await q(Axis(field="i", interval="10")) == {0.0: 2, 10.0: 1, 30.0: 1}


@pytest.mark.anyio
async def test_second_axis(index_docs):
    q = functools.partial(do_query, index_docs)
    assert await q("cat", "subcat") == {("a", "x"): 2, ("a", "y"): 1, ("b", "y"): 1}
    assert await q(Axis(field="date", interval="year"), "cat") == {(_y(2018), "a"): 2, (_y(2020), "a"): 1, (_y(2018), "b"): 1}
    assert await q("cat", Axis(field="date", interval="year")) == {("a", _y(2018)): 2, ("a", _y(2020)): 1, ("b", _y(2018)): 1}


@pytest.mark.anyio
async def test_count(index_docs):
    """Does aggregation without axes work"""
    assert await do_query(index_docs) == {(): 4}
    assert await do_query(index_docs, queries={"text": "text"}) == {(): 2}


@pytest.mark.anyio
async def test_byquery(index_docs):
    """Get number of documents per query"""
    assert await do_query(index_docs, Axis("_query"), queries={"text": "text", "test*": "test*"}) == {"text": 2, "test*": 3}
    assert await do_query(index_docs, Axis("_query"), Axis("subcat"), queries={"text": "text", "test*": "test*"}) == {
        ("text", "x"): 2,
        ("test*", "x"): 1,
        ("test*", "y"): 2,
    }
    assert await do_query(index_docs, Axis("subcat"), Axis("_query"), queries={"text": "text", "test*": "test*"}) == {
        ("x", "text"): 2,
        ("x", "test*"): 1,
        ("y", "test*"): 2,
    }


@pytest.mark.anyio
async def test_metric(index_docs: str):
    """Do metric aggregations (e.g. avg(x)) work?"""

    # Single and double aggregation with axis
    async def q(axes, aggregations):
        return dictset((await query_aggregate(index_docs, axes, aggregations)).as_dicts())

    assert await q([Axis("subcat")], [Aggregation("i", "avg")]) == dictset(
        [{"subcat": "x", "n": 2, "avg_i": 1.5}, {"subcat": "y", "n": 2, "avg_i": 21.0}]
    )
    assert await q([Axis("subcat")], [Aggregation("i", "avg"), Aggregation("i", "max")]) == dictset(
        [{"subcat": "x", "n": 2, "avg_i": 1.5, "max_i": 2.0}, {"subcat": "y", "n": 2, "avg_i": 21.0, "max_i": 31.0}]
    )
    # Aggregation only
    assert await q(None, [Aggregation("i", "avg")]) == dictset([{"n": 4, "avg_i": 11.25}])
    assert await q(None, [Aggregation("i", "avg"), Aggregation("i", "max")]) == dictset(
        [{"n": 4, "avg_i": 11.25, "max_i": 31.0}]
    )

    # Count only
    assert await q([], []) == dictset([{"n": 4}])

    # Check value handling - Aggregation on date fields
    assert await q(None, [Aggregation("date", "max")]) == dictset([{"n": 4, "max_date": "2020-01-01T00:00:00+00:00"}])
    assert await q([Axis("subcat")], [Aggregation("date", "avg")]) == dictset(
        [
            {"subcat": "x", "n": 2, "avg_date": "2018-01-16T12:00:00+00:00"},
            {"subcat": "y", "n": 2, "avg_date": "2019-01-01T00:00:00+00:00"},
        ]
    )


@pytest.mark.anyio
async def test_aggregate_datefunctions(index: str):
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
    await upload(index, docs, fields=dict(date=CreateDocumentField(type="date")))
    assert await q(Axis("date", interval="day")) == {
        date(2018, 1, 1): 2,
        date(2018, 1, 11): 1,
        date(2018, 1, 17): 2,
        date(2018, 3, 7): 1,
    }
    assert await q(Axis("date", interval="dayofweek")) == {"Monday": 2, "Wednesday": 3, "Thursday": 1}
    assert await q(Axis("date", interval="daypart")) == {"Night": 1, "Morning": 3, "Evening": 2}
    assert await q(Axis("date", interval="monthnr")) == {1: 5, 3: 1}
    assert await q(Axis("date", interval="yearnr")) == {2018: 6}
    assert await q(Axis("date", interval="dayofmonth")) == {1: 2, 11: 1, 17: 2, 7: 1}
    assert await q(Axis("date", interval="weeknr")) == {1: 2, 2: 1, 3: 2, 10: 1}
    assert await q(Axis("date", interval="month"), Axis("date", interval="dayofmonth")) == {
        (date(2018, 1, 1), 1): 2,
        (date(2018, 1, 1), 11): 1,
        (date(2018, 1, 1), 17): 2,
        (date(2018, 3, 1), 7): 1,
    }
