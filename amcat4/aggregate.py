"""
Aggregate queries
"""
from datetime import datetime
from typing import Mapping, Iterable, Union, Tuple, Sequence, List

from amcat4.elastic import es, field_type
from amcat4.query import build_body, _normalize_queries


class Axis:
    """
    Class that specifies an aggregation axis
    """
    def __init__(self, field: str = None, interval: str = None, query_name=None):
        if bool(field) + bool(query_name) != 1:
            raise ValueError("Specify field or query_name")
        self.field = field
        self.interval = interval
        self.query_name = query_name


class BoundAxis:
    """
    Class that specifies an aggregation axis bound to an index
    """
    def __init__(self, axis: Axis, index: str):
        self.axis = axis
        self.index = index
        self.ftype = "_query" if axis.field == "_query" else field_type(index, axis.field)

    @property
    def field(self):
        return self.axis.field

    @property
    def interval(self):
        return self.axis.interval

    def query(self):
        if not self.ftype:
            raise ValueError("Please set index before using axis")
        if self.interval:
            if self.ftype == "date":
                return {self.field: {"date_histogram": {"field": self.field, "calendar_interval": self.interval}}}
            else:
                return {self.field: {"histogram": {"field": self.field, "interval": self.interval}}}
        else:
            return {self.field: {"terms": {"field": self.field}}}

    def postprocess(self, value):
        if self.ftype == "date":
            value = datetime.utcfromtimestamp(value / 1000.)
            if self.interval in {"year", "month", "week", "day"}:
                value = value.date()
        return value

    def asdict(self):
        return {"field": self.field, "type": self.ftype, "interval": self.interval}


class AggregateResult:
    def __init__(self, axes: Sequence[BoundAxis], data: List[tuple], value_column: str="n", aggregations=None):
        self.axes = axes
        self.data = data
        self.aggregations = aggregations
        self.value_column = value_column

    def as_dicts(self) -> Iterable[dict]:
        """Return the results as a sequence of {axis1, ..., n} dicts"""
        keys = tuple(ax.field for ax in self.axes) + (self.value_column, )
        if self.aggregations: keys += tuple(self.aggregations.keys())
        for row in self.data:
            yield dict(zip(keys, row))


def _elastic_aggregate(index, sources, queries, filters, aggregations, after_key=None):
    """
    Recursively get all buckets from a composite query
    """
    # [WvA] Not sure if we should get all results ourselves or expose the 'after' pagination.
    #       This might get us in trouble if someone e.g. aggregates on url or day for a large corpus
    after = {"after": after_key} if after_key else {}
    aggr = {"composite": dict(sources=sources, **after)}
    if aggregations:
        aggr['aggregations'] = aggregations
    body = {"size": 0, "aggregations": {"aggr": aggr}}
    if filters or queries:
        q = build_body(queries=queries, filters=filters)
        body["query"] = q["query"]
    result = es().search(index=index, body=body)['aggregations']['aggr']
    yield from result['buckets']
    after_key = result.get('after_key')
    if after_key:
        yield from _elastic_aggregate(index, sources, queries, filters, aggregations, after_key)


def _aggregate_results(index: str, axes: Sequence[BoundAxis], queries: Mapping[str, str],
                       filters: Mapping[str, Mapping], aggregations) -> Iterable[tuple]:
    # TODO: metrics without axes, make n optional (?), turn aggregation into object with postprocess (esp for dates)
    if not axes:
        # No axes, so return total count
        body = build_body(queries=queries, filters=filters)
        count = es().count(index=index, body=body)
        yield count['count'],
    elif axes[0].field == "_query":
        # Run query for each count
        for label, query in queries.items():
            for result_tuple in _aggregate_results(index, axes[1:], {label: query}, filters, aggregations):
                yield (label,) + result_tuple
    else:
        sources = [axis.query() for axis in axes]
        for bucket in _elastic_aggregate(index, sources, queries, filters, aggregations):
            keys = tuple(axis.postprocess(bucket['key'][axis.field]) for axis in axes)
            yield keys + (bucket['doc_count'], ) + tuple(bucket[a]['value'] for a in aggregations)


def query_aggregate(index: str, axes: Sequence[Axis], aggregations=None, *,
                    queries: Union[Mapping[str, str], Sequence[str]] = None,
                    filters: Mapping[str, Mapping] = None) -> AggregateResult:
    """
    Conduct an aggregate query.
    Note that interval queries also yield zero counts for intervening keys without value,
    but only if that is the last axis. [WvA] Not sure if this is desired

    :param index: The name of the elasticsearch index
    :param axis: The primary aggregation axis, should be the name of a field or a dict with keys 'field', 'interval'
    :param axes: Optional additional axes
    :param value_column: Name for the value 'column', default n. This might be expanded for other aggregate values (avg etc)
    :param queries: Optional query string
    :param filters: if not None, a dict of filters: {field: {'value': value}} or
                    {field: {'range': {'gte/gt/lte/lt': value, 'gte/gt/..': value, ..}}
    :return: a pair of (Axis, results), where results is a sequence of tuples
    """
    if any(x.field == "_query" for x in axes[1:]):
        raise ValueError("Only the primary (first) aggregation may be by query")
    _axes = [BoundAxis(axis, index) for axis in axes]
    queries = _normalize_queries(queries)
    data = list(_aggregate_results(index, _axes, queries, filters, aggregations))
    return AggregateResult(_axes, data, value_column="n", aggregations=aggregations)
