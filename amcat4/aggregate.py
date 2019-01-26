"""
Aggregate queries
"""
import json
import logging
from datetime import datetime
from typing import Mapping, Iterable, Tuple, Union

from amcat4.elastic import PREFIX, DOCTYPE, es, field_type


class _Axis:
    """
    Internal helper class that represents an aggregation axis
    """
    def __init__(self, project_name, field, interval=None):
        self.project_name = project_name
        if isinstance(field, dict):
            self.field = field['field']
            self.interval = field.get('interval')
        else:
            self.field = field
            self.interval = interval
        self.ftype = field_type(project_name, self.field)

    def query(self):
        if self.interval:
            if self.ftype == "date":
                return {"aggr": {"date_histogram": {"field": self.field, "interval": self.interval}}}
            else:
                return {"aggr": {"histogram": {"field": self.field, "interval": self.interval}}}
        else:
            return {"aggr": {"terms": {"field": self.field}}}

    def nested_query(self, inner_axes=None):
        q = self.query()
        if inner_axes:
            next_axis, tail = inner_axes[0], inner_axes[1:]
            q['aggr']['aggregations'] = next_axis.nested_query(tail)
        return q

    def postprocess(self, value):
        if self.ftype == "date":
            value = datetime.utcfromtimestamp(value / 1000.)
        return value

    def process(self, result, prefix=(), inner_axes=None):
        """
        Process the elasticsearch results.
        If there are inner axes, call the next axis to process inner results
        """
        if result.get('doc_count_error_upper_bound', 0) > 0:
            logging.warning(json.dumps(result, indent=2))
            raise Exception("Possibly inaccurate result!")  # not sure if check ever useful

        for bucket in result['buckets']:
            key = self.postprocess(bucket['key'])
            if not inner_axes:
                yield prefix + (key, bucket['doc_count'])
            else:
                next_axis, tail = inner_axes[0], inner_axes[1:]
                yield from next_axis.process(bucket['aggr'], prefix + (key,), tail)


def query_aggregate(project_name: str, axis: Union[str, dict], *axes: Union[str, dict],
                    filters: Mapping[str, Mapping] = None) -> Iterable[Tuple]:
    """
    Conduct an aggregate query.
    Note that interval queries also yield zero counts for intervening keys without value,
    but only if that is the last axis. [WvA] Not sure if this is desired

    :param project_name:
    :param axis: The primary aggregation axis, should be the name of a field (options for date/int ranges forthcoming)
    :param axes: Optional additional axes
    :param filters: if not None, a dict of filters: {field: {'value': value}} or
                    {field: {'range': {'gte/gt/lte/lt': value, 'gte/gt/..': value, ..}}
    :return: a sequence of (axis-value, [axis2-value, ...], aggregate-value) tuples
    """

    index = "".join([PREFIX, project_name])

    axes = [_Axis(project_name, x) for x in (axis, ) + axes]
    aggr = axes[0].nested_query(axes[1:])

    result = es.search(index, DOCTYPE, body=dict(size=0, aggregations=aggr))['aggregations']['aggr']
    return axes[0].process(result, inner_axes=axes[1:])
