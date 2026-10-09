"""
Aggregation for the postgres backend.

Aggregations are plain SQL GROUP BY queries over the documents selected by the BM25 index. Date intervals
(year, month, ...) use date_trunc, derived date parts (day of week, month number, ...) use the same
expressions as the filters. Results are returned as rows, sorted by the axes.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from psycopg import sql

from amcat4.postgres.fields import DATE_DERIVED, FieldInfo, QueryError
from amcat4.postgres.filters import DATE_TRUNC, field_sql

MetricFunction = Literal["sum", "avg", "min", "max", "count"]


@dataclass
class Axis:
    field: str
    interval: str | None = None

    @property
    def name(self) -> str:
        return f"{self.field}_{self.interval}" if self.interval else self.field


RAW_GROUP_TYPES = {"keyword", "url", "image", "video", "audio", "text"}


def axis_expr(axis: Axis, fs: list[FieldInfo], lateral_alias: str) -> tuple[sql.Composable, sql.Composable | None]:
    """Returns the SQL expression for the axis, and an optional LATERAL join (for tags)"""
    ftype = fs[0].type
    if ftype == "tag":
        arrays = [sql.SQL("documents.exact_fields->{}").format(sql.Literal(f.key)) for f in fs]
        arr = arrays[0] if len(arrays) == 1 else sql.SQL("coalesce({})").format(sql.SQL(", ").join(arrays))
        lateral = sql.SQL("CROSS JOIN LATERAL jsonb_array_elements_text({}) AS {}(value)").format(
            arr, sql.Identifier(lateral_alias)
        )
        return sql.SQL("{}.value").format(sql.Identifier(lateral_alias)), lateral

    if (axis.interval is None and ftype in RAW_GROUP_TYPES) or (ftype == "date" and axis.interval in DATE_DERIVED):
        # Group on the raw json value (or the derived date key, so no date expression is needed), and convert
        # the values to the right type afterwards. Postgres does the grouping: pg_search can only group inside
        # the index on indexed columns, not on json expressions like this.
        keys = [f.key if axis.interval is None else f.derived_key(axis.interval) for f in fs]
        raws = [sql.SQL("documents.exact_fields->>{}").format(sql.Literal(k)) for k in keys]
        return (raws[0] if len(raws) == 1 else sql.SQL("coalesce({})").format(sql.SQL(", ").join(raws))), None

    exprs = [field_sql(f) for f in fs]
    x = exprs[0] if len(exprs) == 1 else sql.SQL("coalesce({})").format(sql.SQL(", ").join(exprs))
    if axis.interval is None:
        return x, None
    if ftype == "date":
        if axis.interval in DATE_TRUNC:
            return sql.SQL("date_trunc({}, {})").format(sql.Literal(axis.interval), x), None
        raise QueryError(f"Unknown date interval: {axis.interval}")
    if ftype in ("number", "integer"):
        interval = float(axis.interval)
        return sql.SQL("floor({} / {}) * {}").format(x, sql.Literal(interval), sql.Literal(interval)), None
    raise QueryError(f"Interval not supported for {ftype} field {axis.field}")


def postprocess_value(value: Any, axis: Axis, ftype: str) -> Any:
    """Convert the (textual) group value to the right type"""
    if value is None:
        return None
    if isinstance(value, datetime):
        if axis.interval == "quarter":
            return value.date()
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value
    if isinstance(value, Decimal):
        return int(value) if ftype == "integer" and axis.interval is None else float(value)
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
        case "boolean" if isinstance(value, bool):
            return value
        case "boolean":
            return value == "true"
    return value


def sort_key(row: dict, axes: list[Axis]) -> tuple:
    # sort by axis values (None last), with values of mixed types compared as strings
    return tuple((row[ax.name] is None, str(type(row[ax.name])), row[ax.name] or 0) for ax in axes)
