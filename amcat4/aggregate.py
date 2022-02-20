"""
Aggregate queries
"""
from datetime import datetime
from typing import Mapping, Iterable, Union, Tuple, Sequence, List, Dict, Optional

from amcat4.elastic import es, field_type
from amcat4.query import build_body, _normalize_queries


class Axis:
    """
    Class that specifies an aggregation axis
    """
    def __init__(self, field: str, interval: str = None):
        self.field = field
        self.interval = interval


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


class Aggregation:
    """
    Specification of a single aggregation, that is, field and aggregation function
    """
    def __init__(self, field: str, function: str, name: str = None):
        self.field = field
        self.function = function
        self.name = name or f"{function}_{field}"


class BoundAggregation:
    """
    Aggregation bound to an index (for field type information)
    """
    def __init__(self, aggregation: Aggregation, index: str):
        self.aggregation = aggregation
        self.index = index
        self.ftype = field_type(index, self.aggregation.field)

    @property
    def name(self):
        return self.aggregation.name

    @property
    def function(self):
        return self.aggregation.function

    @property
    def field(self):
        return self.aggregation.field

    def dsl_item(self):
        return self.name, {self.function: {"field": self.field}}

    def get_value(self, bucket: dict):
        result = bucket[self.name]['value']
        if self.ftype == "date":
            result = datetime.utcfromtimestamp(result / 1000.)
        return result

    def asdict(self):
        return {"field": self.field, "type": self.ftype, "function": self.function, "name": self.name}


def aggregation_dsl(aggregations: Iterable[BoundAggregation]) -> dict:
    """Get the aggregation DSL dict for a list of aggregations"""
    return dict(a.dsl_item() for a in aggregations)


class AggregateResult:
    def __init__(self, axes: Sequence[BoundAxis], aggregations: List[BoundAggregation],
                 data: List[tuple], count_column: str = "n"):
        self.axes = axes
        self.data = data
        self.aggregations = aggregations
        self.count_column = count_column

    def as_dicts(self) -> Iterable[dict]:
        """Return the results as a sequence of {axis1, ..., n} dicts"""
        keys = tuple(ax.field for ax in self.axes) + (self.count_column, )
        if self.aggregations:
            keys += tuple(a.name for a in self.aggregations)
        for row in self.data:
            yield dict(zip(keys, row))


def _bare_aggregate(index: str, queries, filters, aggregations: Sequence[BoundAggregation]) -> Tuple[int, dict]:
    """
    Aggregate without sources/group_by.
    Returns a tuple of doc count and aggregegations (doc_count, {metric: value})
    """
    kargs = {}
    if filters or queries:
        q = build_body(queries=queries, filters=filters)
        kargs["query"] = q["query"]
    result = es().search(index=index, size=0, aggregations=aggregation_dsl(aggregations), **kargs)
    return result["hits"]["total"]["value"], result['aggregations']


def _elastic_aggregate(index: str, sources, queries, filters, aggregations: Sequence[BoundAggregation],
                       after_key=None) -> Iterable[dict]:
    """
    Recursively get all buckets from a composite query.
    Yields 'buckets' consisting of {key: {axis: value}, doc_count: <number>}
    """
    # [WvA] Not sure if we should get all results ourselves or expose the 'after' pagination.
    #       This might get us in trouble if someone e.g. aggregates on url or day for a large corpus
    after = {"after": after_key} if after_key else {}
    aggr: Dict[str, Dict[str, dict]] = {"aggr": {}}
    aggr["aggr"]["composite"] = dict(sources=sources, **after)
    if aggregations:
        aggr["aggr"]['aggregations'] = aggregation_dsl(aggregations)
    kargs = {}
    if filters or queries:
        q = build_body(queries=queries, filters=filters)
        kargs["query"] = q["query"]
    result = es().search(index=index, size=0, aggregations=aggr, **kargs)['aggregations']['aggr']
    yield from result['buckets']
    after_key = result.get('after_key')
    if after_key:
        yield from _elastic_aggregate(index, sources, queries, filters, aggregations, after_key)


def _aggregate_results(index: str, axes: List[BoundAxis], queries: Mapping[str, str],
                       filters: Optional[Mapping[str, Mapping]], aggregations: List[BoundAggregation]) -> Iterable[tuple]:
    if not axes:
        # No axes, so return aggregations (or total count) only
        if aggregations:
            count, results = _bare_aggregate(index, queries, filters, aggregations)
            yield (count,) + tuple(a.get_value(results) for a in aggregations)
        else:
            result = es().count(index=index, body=build_body(queries=queries, filters=filters))
            yield result['count'],
    elif any(ax.field == "_query" for ax in axes):
        # Strip off first axis and run separate aggregation for each query
        i = [ax.field for ax in axes].index("_query")
        _axes = axes[:i] + axes[(i+1):]
        for label, query in queries.items():
            for result_tuple in _aggregate_results(index, _axes, {label: query}, filters, aggregations):
                # insert label into the right position on the result tuple
                yield result_tuple[:i] + (label,) + result_tuple[i:]
    else:
        # Run an aggregation with one or more axes
        sources = [axis.query() for axis in axes]
        for bucket in _elastic_aggregate(index, sources, queries, filters, aggregations):
            row = tuple(axis.postprocess(bucket['key'][axis.field]) for axis in axes)
            row += (bucket['doc_count'], )
            if aggregations:
                row += tuple(a.get_value(bucket) for a in aggregations)
            yield row


def query_aggregate(index: str, axes: Sequence[Axis] = None, aggregations: Sequence[Aggregation] = None, *,
                    queries: Union[Mapping[str, str], Sequence[str]] = None,
                    filters: Mapping[str, Mapping] = None) -> AggregateResult:
    """
    Conduct an aggregate query.
    Note that interval queries also yield zero counts for intervening keys without value,
    but only if that is the last axis. [WvA] Not sure if this is desired

    :param index: The name of the elasticsearch index
    :param axes: Aggregation axes
    :param aggregations: Aggregation fields
    :param queries: Optional query string
    :param filters: if not None, a dict of filters: {field: {'value': value}} or
                    {field: {'range': {'gte/gt/lte/lt': value, 'gte/gt/..': value, ..}}
    :return: a pair of (Axis, results), where results is a sequence of tuples
    """
    if axes and len([x.field == "_query" for x in axes[1:]]) > 1:
        raise ValueError("Only one aggregation axis may be by query")
    _axes = [BoundAxis(axis, index) for axis in axes] if axes else []
    _aggregations = [BoundAggregation(a, index) for a in aggregations] if aggregations else []
    queries = _normalize_queries(queries)
    data = list(_aggregate_results(index, _axes, queries, filters, _aggregations))
    return AggregateResult(_axes, _aggregations, data, count_column="n", )
