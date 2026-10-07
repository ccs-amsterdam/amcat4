"""
Aggregation for the postgres backend.

Aggregations are plain SQL GROUP BY queries over the documents selected by the BM25 index. Date intervals
(year, month, ...) use date_trunc, derived date parts (day of week, month number, ...) use the same
expressions as the filters. Results are returned as rows, sorted by the axes.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from psycopg import AsyncConnection, sql

from amcat4.postgres.fields import FieldInfo, FieldSet, QueryError
from amcat4.postgres.filters import DATE_PARTS, DATE_TRUNC, field_sql
from amcat4.postgres.search import SearchQuery, compile_search

MetricFunction = Literal["sum", "avg", "min", "max", "count"]


@dataclass
class Axis:
    field: str
    interval: str | None = None

    @property
    def name(self) -> str:
        return f"{self.field}_{self.interval}" if self.interval else self.field


@dataclass
class Metric:
    field: str
    function: MetricFunction

    @property
    def name(self) -> str:
        return f"{self.function}_{self.field}"


def _axis_expr(axis: Axis, fs: list[FieldInfo], lateral_alias: str) -> tuple[sql.Composable, sql.Composable | None]:
    """Returns the SQL expression for the axis, and an optional LATERAL join (for tags)"""
    ftype = fs[0].type
    if ftype == "tag":
        arrays = [sql.SQL("documents.meta_data->{}").format(sql.Literal(f.key)) for f in fs]
        arr = arrays[0] if len(arrays) == 1 else sql.SQL("coalesce({})").format(sql.SQL(", ").join(arrays))
        lateral = sql.SQL("CROSS JOIN LATERAL jsonb_array_elements_text({}) AS {}(value)").format(
            arr, sql.Identifier(lateral_alias)
        )
        return sql.SQL("{}.value").format(sql.Identifier(lateral_alias)), lateral

    exprs = [field_sql(f) for f in fs]
    x = exprs[0] if len(exprs) == 1 else sql.SQL("coalesce({})").format(sql.SQL(", ").join(exprs))
    if axis.interval is None:
        return x, None
    if ftype == "date":
        if axis.interval in DATE_TRUNC:
            return sql.SQL("date_trunc({}, {})").format(sql.Literal(axis.interval), x), None
        if axis.interval in DATE_PARTS:
            return sql.SQL(DATE_PARTS[axis.interval].replace("{x}", "{0}")).format(x), None  # type: ignore[arg-type]
        raise QueryError(f"Unknown date interval: {axis.interval}")
    if ftype in ("number", "integer"):
        interval = float(axis.interval)
        return sql.SQL("floor({} / {}) * {}").format(x, sql.Literal(interval), sql.Literal(interval)), None
    raise QueryError(f"Interval not supported for {ftype} field {axis.field}")


def _metric_expr(metric: Metric, fieldset: FieldSet) -> sql.Composable:
    fs = fieldset.resolve(metric.field)
    if fs[0].type not in ("number", "integer", "date") and metric.function != "count":
        raise QueryError(f"Cannot compute {metric.function} of {fs[0].type} field {metric.field}")
    exprs = [field_sql(f) for f in fs]
    x = exprs[0] if len(exprs) == 1 else sql.SQL("coalesce({})").format(sql.SQL(", ").join(exprs))
    return sql.SQL("{}({})").format(sql.SQL(metric.function), x)


def _postprocess(value: Any, axis: Axis) -> Any:
    if isinstance(value, datetime) and axis.interval in ("year", "quarter", "month", "week", "day"):
        return value.date()
    if axis.interval in ("monthnr", "yearnr", "decade", "dayofmonth", "weeknr") and isinstance(value, (int, float, Decimal)):
        return int(value)
    return value


async def aggregate(
    conn: AsyncConnection,
    fieldset: FieldSet,
    query: SearchQuery,
    axes: list[Axis],
    metrics: list[Metric] | None = None,
    limit: int = 1000,
) -> list[dict]:
    """
    Aggregate documents by the given axes (with optional metrics). The special axis field '_query' splits
    the results by query label (one SQL query per label).
    """
    metrics = metrics or []
    if any(ax.field == "_query" for ax in axes):
        if not query.queries:
            raise QueryError("Queries must be specified when aggregating by query")
        other_axes = [ax for ax in axes if ax.field != "_query"]
        rows = []
        for label, q in query.queries.items():
            sub = SearchQuery(queries={label: q}, filters=query.filters, ids=query.ids)
            for row in await aggregate(conn, fieldset, sub, other_axes, metrics, limit):
                rows.append({"_query": label, **row})
        return rows

    c = compile_search(fieldset, query)
    selects: list[sql.Composable] = []
    laterals: list[sql.Composable] = []
    for i, axis in enumerate(axes):
        expr, lateral = _axis_expr(axis, fieldset.resolve(axis.field), f"tag_{i}")
        selects.append(sql.SQL("{} AS {}").format(expr, sql.Identifier(axis.name)))
        if lateral is not None:
            laterals.append(lateral)
    selects.append(sql.SQL("count(*) AS n"))
    for metric in metrics:
        selects.append(sql.SQL("{} AS {}").format(_metric_expr(metric, fieldset), sql.Identifier(metric.name)))

    group = sql.SQL("")
    if axes:
        positions = sql.SQL(", ").join(sql.Literal(i + 1) for i in range(len(axes)))
        group = sql.SQL("GROUP BY {} ORDER BY {}").format(positions, positions)
    stmt = sql.SQL("SELECT {} FROM documents {} WHERE {} {} LIMIT %s").format(
        sql.SQL(", ").join(selects), sql.SQL(" ").join(laterals), c.where, group
    )
    cur = await conn.execute(stmt, [*c.params, limit])
    rows = await cur.fetchall()
    out = []
    for row in rows:
        d = dict(row)  # type: ignore[arg-type]
        for axis in axes:
            d[axis.name] = _postprocess(d[axis.name], axis)
        for metric in metrics:
            if isinstance(d[metric.name], (date, datetime)) or d[metric.name] is None:
                continue
            d[metric.name] = float(d[metric.name])
        out.append(d)
    return out
