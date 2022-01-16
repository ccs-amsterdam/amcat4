"""
Aggregate queries
"""
from collections import namedtuple
from datetime import datetime
from typing import Mapping, Iterable, Union, Tuple, Sequence, NamedTuple

from amcat4.elastic import es, field_type
from amcat4.query import build_body, _normalize_queries


class Axis:
    """
    Class that represents an aggregation axis
    """
    def __init__(self, index: str, field: Union[str, dict], interval=None):
        if isinstance(field, dict):
            self.field = field['field']
            self.interval = field.get('interval')
        else:
            self.field = field
            self.interval = interval
        self.ftype = field_type(index, self.field)

    def query(self):
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


def _get_aggregates(index, sources, queries, filters, after_key=None):
    """
    Recursively get all buckets from a composite query
    """
    # [WvA] Not sure if we should get all results ourselves or expose the 'after' pagination.
    #       This might get us in trouble if someone e.g. aggregates on url or day for a large corpus
    after = {"after": after_key} if after_key else {}
    body = {"size": 0, "aggregations": {"aggr": {"composite": dict(sources=sources, **after)}}}
    if filters or queries:
        q = build_body(queries=queries, filters=filters)
        body["query"] = q["query"]
    result = es.search(index=index, body=body)['aggregations']['aggr']
    yield from result['buckets']
    after_key = result.get('after_key')
    if after_key:
        yield from _get_aggregates(index, sources, queries, filters, after_key)


def query_aggregate(index: str, axis: Union[str, dict], *more_axes: Union[str, dict],
                    value="n", queries: Union[Mapping[str, str], Sequence[str]] = None,
                    filters: Mapping[str, Mapping] = None) -> Tuple[Iterable[Axis], Iterable[NamedTuple]]:
    """
    Conduct an aggregate query.
    Note that interval queries also yield zero counts for intervening keys without value,
    but only if that is the last axis. [WvA] Not sure if this is desired

    :param index: The name of the elasticsearch index
    :param axis: The primary aggregation axis, should be the name of a field or a dict with keys 'field', 'interval'
    :param axes: Optional additional axes
    :param value: Name for the value 'column', default n. This might be expanded for other aggregate values (avg etc)
    :param queries: Optional query string
    :param filters: if not None, a dict of filters: {field: {'value': value}} or
                    {field: {'range': {'gte/gt/lte/lt': value, 'gte/gt/..': value, ..}}
    :return: a pair of (Axis, results), where results is a sequence of (axis-value, [axis2-value, ...], aggregate-value) tuples
    """
    axes = [Axis(index, x) for x in (axis, ) + more_axes]
    names = [x.field for x in axes] + [value]
    nt = namedtuple("Bucket", names)  # type: ignore
    sources = [axis.query() for axis in axes]
    queries = _normalize_queries(queries)

    def _process(axes, bucket) -> NamedTuple:
        values = [axis.postprocess(bucket['key'][axis.field]) for axis in axes] + [bucket['doc_count']]
        return nt(*values)  # noqa
    results = [_process(axes, bucket)
               for bucket in _get_aggregates(index, sources, queries, filters)]
    return axes, results
