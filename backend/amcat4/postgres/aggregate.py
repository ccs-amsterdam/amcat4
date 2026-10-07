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

from amcat4.postgres.fields import DATE_DERIVED, FieldInfo, FieldSet, QueryError
from amcat4.postgres.filters import DATE_TRUNC, field_sql
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

    if axis.interval is None or (ftype == "date" and axis.interval in DATE_DERIVED):
        # Group on the raw json value (or the derived date key), which pg_search can aggregate inside the
        # index. Values are converted to the right type afterwards.
        keys = [f.key if axis.interval is None else f.derived_key(axis.interval) for f in fs]
        raws = [sql.SQL("documents.meta_data->>{}").format(sql.Literal(k)) for k in keys]
        return (raws[0] if len(raws) == 1 else sql.SQL("coalesce({})").format(sql.SQL(", ").join(raws))), None

    exprs = [field_sql(f) for f in fs]
    x = exprs[0] if len(exprs) == 1 else sql.SQL("coalesce({})").format(sql.SQL(", ").join(exprs))
    if ftype == "date":
        if axis.interval in DATE_TRUNC:
            return sql.SQL("date_trunc({}, {})").format(sql.Literal(axis.interval), x), None
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


def _postprocess(value: Any, axis: Axis, ftype: str) -> Any:
    """Convert the (textual) group value to the right type"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date() if axis.interval == "quarter" else value
    if isinstance(value, Decimal):
        return float(value)
    if ftype == "date" and axis.interval is None:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    match axis.interval if ftype == "date" else ftype:
        case "year":
            return date(int(value), 1, 1)
        case "month":
            return date.fromisoformat(value + "-01")
        case "week" | "day":
            return date.fromisoformat(value)
        case "monthnr" | "yearnr" | "decade" | "dayofmonth" | "weeknr" | "integer":
            return int(value)
        case "number":
            return float(value)
        case "boolean":
            return value == "true"
    return value


def _sort_key(row: dict, axes: list[Axis]) -> tuple:
    # sort by axis values (None last), with values of mixed types compared as strings
    return tuple((row[ax.name] is None, str(type(row[ax.name])), row[ax.name] or 0) for ax in axes)


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

    # No ORDER BY / LIMIT in SQL: that prevents pg_search from running the aggregation inside the index.
    # We sort the (typed) results in python instead.
    group = sql.SQL("")
    if axes:
        group = sql.SQL("GROUP BY {}").format(sql.SQL(", ").join(sql.Literal(i + 1) for i in range(len(axes))))
    stmt = sql.SQL("SELECT {} FROM documents {} WHERE {} {}").format(
        sql.SQL(", ").join(selects), sql.SQL(" ").join(laterals), c.where, group
    )
    cur = await conn.execute(stmt, c.params)
    rows = await cur.fetchall()
    out = []
    for row in rows:
        d = dict(row)  # type: ignore[arg-type]
        for axis in axes:
            d[axis.name] = _postprocess(d[axis.name], axis, fieldset.type(axis.field))
        for metric in metrics:
            if isinstance(d[metric.name], (date, datetime)) or d[metric.name] is None:
                continue
            d[metric.name] = float(d[metric.name])
        out.append(d)
    out.sort(key=lambda row: _sort_key(row, axes))
    return out[:limit]
