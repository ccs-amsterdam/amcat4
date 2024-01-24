"""
Aggregate queries
"""
from datetime import datetime
from typing import Mapping, Iterable, Union, Tuple, Sequence, List, Dict

from amcat4.date_mappings import interval_mapping
from amcat4.elastic import es
from amcat4.fields import get_fields
from amcat4.query import build_body
from amcat4.models import Field, FilterSpec


def _combine_mappings(mappings):
    result = {}
    for mapping in mappings:
        if mapping:
            result.update(mapping)
    return result


class Axis:
    """
    Class that specifies an aggregation axis
    """

    def __init__(self, field: str, interval: str | None = None, name: str | None = None, field_type: str | None = None):
        self.field = field
        self.interval = interval
        self.ftype = field_type
        if name:
            self.name = name
        elif interval:
            self.name = f"{field}_{interval}"
        else:
            self.name = field

    def __repr__(self):
        return f"<Axis field={self.field} fytpe={self.ftype}>"

    def query(self):
        if not self.ftype:
            raise ValueError("Please set index before using axis")
        if self.interval:
            if self.ftype == "date":
                if m := interval_mapping(self.interval):
                    return {self.name: {"terms": {"field": m.fieldname(self.field)}}}
                return {self.name: {"date_histogram": {"field": self.field, "calendar_interval": self.interval}}}
            else:
                return {self.name: {"histogram": {"field": self.field, "interval": self.interval}}}
        else:
            return {self.name: {"terms": {"field": self.field}}}

    def get_value(self, values):
        value = values[self.name]
        if m := interval_mapping(self.interval):
            value = m.postprocess(value)
        elif self.ftype == "date":
            value = datetime.utcfromtimestamp(value / 1000.0)
            if self.interval in {"year", "month", "week", "day"}:
                value = value.date()
        return value

    def asdict(self):
        return {"name": self.name, "field": self.field, "type": self.ftype, "interval": self.interval}

    def runtime_mappings(self):
        if m := interval_mapping(self.interval):
            return m.mapping(self.field)


class Aggregation:
    """
    Specification of a single aggregation, that is, field and aggregation function
    """

    def __init__(self, field: str, function: str, name: str | None = None, ftype: str | None = None):
        self.field = field
        self.function = function
        self.name = name or f"{function}_{field}"
        self.ftype = ftype

    def dsl_item(self):
        return self.name, {self.function: {"field": self.field}}

    def get_value(self, bucket: dict):
        result = bucket[self.name]["value"]
        if result and self.ftype == "date":
            result = datetime.utcfromtimestamp(result / 1000.0)
        return result

    def asdict(self):
        return {"field": self.field, "type": self.ftype, "function": self.function, "name": self.name}


def aggregation_dsl(aggregations: Iterable[Aggregation]) -> dict:
    """Get the aggregation DSL dict for a list of aggregations"""
    return dict(a.dsl_item() for a in aggregations)


class AggregateResult:
    def __init__(self, axes: Sequence[Axis], aggregations: List[Aggregation], data: List[tuple], count_column: str = "n"):
        self.axes = axes
        self.data = data
        self.aggregations = aggregations
        self.count_column = count_column

    def as_dicts(self) -> Iterable[dict]:
        """Return the results as a sequence of {axis1, ..., n} dicts"""
        keys = tuple(ax.name for ax in self.axes) + (self.count_column,)
        if self.aggregations:
            keys += tuple(a.name for a in self.aggregations)
        for row in self.data:
            yield dict(zip(keys, row))


def _bare_aggregate(index: str | list[str], queries, filters, aggregations: Sequence[Aggregation]) -> Tuple[int, dict]:
    """
    Aggregate without sources/group_by.
    Returns a tuple of doc count and aggregegations (doc_count, {metric: value})
    """
    body = build_body(queries=queries, filters=filters) if filters or queries else {}
    index = index if isinstance(index, str) else ",".join(index)
    aresult = es().search(index=index, size=0, aggregations=aggregation_dsl(aggregations), **body)
    cresult = es().count(index=index, **body)
    return cresult["count"], aresult["aggregations"]


def _elastic_aggregate(
    index: str | list[str],
    sources,
    queries,
    filters,
    aggregations: list[Aggregation],
    runtime_mappings: dict[str, Mapping] | None = None,
    after_key=None,
) -> Iterable[dict]:
    """
    Recursively get all buckets from a composite query.
    Yields 'buckets' consisting of {key: {axis: value}, doc_count: <number>}
    """
    # [WvA] Not sure if we should get all results ourselves or expose the 'after' pagination.
    #       This might get us in trouble if someone e.g. aggregates on url or day for a large corpus
    after = {"after": after_key} if after_key else {}
    aggr: Dict[str, Dict[str, dict]] = {"aggs": {"composite": dict(sources=sources, **after)}}
    if aggregations:
        aggr["aggs"]["aggregations"] = aggregation_dsl(aggregations)
    kargs = {}
    if filters or queries:
        q = build_body(queries=queries, filters=filters)
        kargs["query"] = q["query"]
    result = es().search(
        index=index if isinstance(index, str) else ",".join(index),
        size=0,
        aggregations=aggr,
        runtime_mappings=runtime_mappings,
        **kargs,
    )
    if failure := result.get("_shards", {}).get("failures"):
        raise Exception(f"Error on running aggregate search: {failure}")
    yield from result["aggregations"]["aggs"]["buckets"]
    after_key = result["aggregations"]["aggs"].get("after_key")
    if after_key:
        yield from _elastic_aggregate(
            index, sources, queries, filters, aggregations, runtime_mappings=runtime_mappings, after_key=after_key
        )


def _aggregate_results(
    index: Union[str, List[str]],
    axes: List[Axis],
    queries: dict[str, str] | None,
    filters: dict[str, FilterSpec] | None,
    aggregations: List[Aggregation],
) -> Iterable[tuple]:
    if not axes:
        # No axes, so return aggregations (or total count) only
        if aggregations:
            count, results = _bare_aggregate(index, queries, filters, aggregations)
            yield (count,) + tuple(a.get_value(results) for a in aggregations)
        else:
            result = es().count(
                index=index if isinstance(index, str) else ",".join(index), **build_body(queries=queries, filters=filters)
            )
            yield result["count"],
    elif any(ax.field == "_query" for ax in axes):
        if queries is None:
            raise ValueError("Queries must be specified when aggregating by query")
        # Strip off _query axis and run separate aggregation for each query
        i = [ax.field for ax in axes].index("_query")
        _axes = axes[:i] + axes[(i + 1) :]
        for label, query in queries.items():
            for result_tuple in _aggregate_results(index, _axes, {label: query}, filters, aggregations):
                # insert label into the right position on the result tuple
                yield result_tuple[:i] + (label,) + result_tuple[i:]
    else:
        # Run an aggregation with one or more axes
        sources = [axis.query() for axis in axes]
        runtime_mappings = _combine_mappings(axis.runtime_mappings() for axis in axes)
        for bucket in _elastic_aggregate(index, sources, queries, filters, aggregations, runtime_mappings):
            row = tuple(axis.get_value(bucket["key"]) for axis in axes)
            row += (bucket["doc_count"],)
            if aggregations:
                row += tuple(a.get_value(bucket) for a in aggregations)
            yield row


def query_aggregate(
    index: str | list[str],
    axes: list[Axis] | None = None,
    aggregations: list[Aggregation] | None = None,
    *,
    queries: dict[str, str] | None = None,
    filters: dict[str, FilterSpec] | None = None,
) -> AggregateResult:
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

    all_fields: dict[str, Field] = dict()
    indices = index if isinstance(index, list) else [index]
    for index in indices:
        index_fields = get_fields(index)
        for field_name, field in index_fields.items():
            if field_name not in all_fields:
                all_fields[field_name] = field
            else:
                if field.type != all_fields[field_name].type:
                    raise ValueError(f"Type of {field_name} is not the same in all indices")
        all_fields.update(get_fields(index))

    if not axes:
        axes = []
    for axis in axes:
        axis.ftype = "_query" if axis.field == "_query" else all_fields[axis.field].type
    if not aggregations:
        aggregations = []
    for aggregation in aggregations:
        aggregation.ftype = all_fields[aggregation.field].type
    data = list(_aggregate_results(index, axes, queries, filters, aggregations))
    return AggregateResult(
        axes,
        aggregations,
        data,
        count_column="n",
    )
