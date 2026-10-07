"""
Filters for the postgres backend.

A filter compiles to pg_search json clauses where possible (so filtering happens inside the BM25 index),
and to plain SQL conditions otherwise (currently only 'exists' on text fields). Date part filters (month number,
day of week) use the derived keys that are stored for every date field.
"""

from dataclasses import dataclass, field
from typing import Any

from psycopg import sql

from amcat4.models import FilterSpec
from amcat4.postgres.fields import DATE_DERIVED, FieldInfo, FieldSet, QueryError, normalize_value
from amcat4.postgres.querystring import range_query


def field_sql(f: FieldInfo, table: str = "documents") -> sql.Composable:
    """SQL expression for the (typed) value of a field"""
    raw = sql.SQL("{}.{}->>{}").format(sql.Identifier(table), sql.Identifier(f.column), sql.Literal(f.key))
    match f.type:
        case "number" | "integer":
            return sql.SQL("({})::numeric").format(raw)
        case "boolean":
            return sql.SQL("({})::boolean").format(raw)
        case "date":
            # timestamptz cast of a fixed-format UTC string; AT TIME ZONE gives a UTC timestamp for date parts
            return sql.SQL("(({})::timestamptz AT TIME ZONE 'UTC')").format(raw)
        case _:
            return raw


# Date intervals that are computed in SQL for aggregation (other intervals use the derived keys, see fields.py)
DATE_TRUNC = {"quarter", "hour", "minute"}


@dataclass
class CompiledFilters:
    json_clauses: list[dict] = field(default_factory=list)
    sql_clauses: list[sql.Composable] = field(default_factory=list)


def _value(f: FieldInfo, value: Any) -> Any:
    v = normalize_value(value, f.type)
    return v[0] if isinstance(v, list) else v


def compile_filters(filters: dict[str, FilterSpec], fieldset: FieldSet) -> CompiledFilters:
    """
    Compile filters. All filters must match (AND). For multi-project queries, a field can have a different
    storage key per project, so each filter is an OR over the project-specific fields.
    """
    out = CompiledFilters()
    for name, spec in filters.items():
        json_alternatives, sql_alternatives = [], []
        for f in fieldset.resolve(name):
            json_clauses, sql_clauses = _compile_filter(f, spec)
            json_alternatives.append(_all_of_json(json_clauses))
            sql_alternatives.append(sql.SQL(" AND ").join(sql_clauses) if sql_clauses else None)
        if any(sql_alternatives):
            # Storage keys are unique per project, so a document can only match the alternative of its own
            # project. This means we can OR the json parts and the sql parts separately.
            out.sql_clauses.append(
                sql.SQL("({})").format(sql.SQL(" OR ").join(a if a is not None else sql.SQL("TRUE") for a in sql_alternatives))
            )
        json_alternatives = [j for j in json_alternatives if j is not None]
        if json_alternatives:
            out.json_clauses.append(
                json_alternatives[0] if len(json_alternatives) == 1 else {"boolean": {"should": json_alternatives}}
            )
    return out


def _all_of_json(clauses: list[dict]) -> dict | None:
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"boolean": {"must": clauses}}


def _compile_filter(f: FieldInfo, spec: FilterSpec) -> tuple[list[dict], list[sql.Composable]]:
    d = spec.model_dump(exclude_none=True)
    clauses: list[dict] = []
    sql_clauses: list[sql.Composable] = []

    values = d.pop("values", None)
    if "value" in d:
        values = (values or []) + [d.pop("value")]
    if values is not None:
        if f.type == "text":
            clauses.append({"boolean": {"should": [{"match": {"field": f.path, "value": str(v)}} for v in values]}})
        elif f.type == "date":
            clauses.append({"boolean": {"should": [range_query(f, v, v) for v in values]}})
        else:
            clauses.append({"boolean": {"should": [{"term": {"field": f.path, "value": _value(f, v)}} for v in values]}})

    bounds = {k: d.pop(k) for k in ("gt", "gte", "lt", "lte") if k in d}
    if bounds:
        lower = bounds.get("gte", bounds.get("gt"))
        upper = bounds.get("lte", bounds.get("lt"))
        clauses.append(range_query(f, lower, upper, "gt" not in bounds, "lt" not in bounds))

    if "exists" in d:
        exists = d.pop("exists")
        if f.column == "meta_data":
            q = {"exists": {"field": f.path}}
            clauses.append(q if exists else {"boolean": {"must": [{"all": None}], "must_not": [q]}})
        else:
            # pg_search 'exists' requires columnar fields, so for text we check the jsonb key in SQL
            cond = sql.SQL("{}.{} ? {}").format(sql.Identifier("documents"), sql.Identifier(f.column), sql.Literal(f.key))
            sql_clauses.append(cond if exists else sql.SQL("NOT ({})").format(cond))

    for part in list(d.keys()):
        if part in DATE_DERIVED:
            if f.type != "date":
                raise QueryError(f"Filter {part} requires a date field, {f.name} is {f.type}")
            clauses.append({"term": {"field": f.derived_path(part), "value": d.pop(part)}})

    if d:
        raise QueryError(f"Unknown filter type(s): {d}")
    return clauses, sql_clauses
