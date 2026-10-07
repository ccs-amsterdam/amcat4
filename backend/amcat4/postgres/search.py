"""
Searching documents in the postgres backend.

A search is a single SQL query on the documents table. Everything that can be expressed as a pg_search query
(project selection, query string, most filters) is combined into one json query, so it is evaluated inside the
BM25 index. Remaining conditions are added as plain SQL.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from psycopg import AsyncConnection, sql
from psycopg.types.json import Jsonb

from amcat4.models import FilterSpec, SnippetParams
from amcat4.postgres.fields import FieldInfo, FieldSet, QueryError
from amcat4.postgres.filters import compile_filters, field_sql
from amcat4.postgres.querystring import query_string_to_json
from amcat4.postgres.snippets import byte_to_char_positions, make_snippet
from amcat4.postgres.snippets import highlight as highlight_text


@dataclass
class SearchQuery:
    """The 'where' part of a search: which documents match"""

    queries: dict[str, str] | None = None  # {label: query string}, combined with OR
    filters: dict[str, FilterSpec] | None = None
    ids: list[str] | None = None


@dataclass
class CompiledSearch:
    json_query: dict
    where: sql.Composable
    params: list[Any] = field(default_factory=list)


def project_clause(project_pks: list[int]) -> dict:
    terms = [{"term": {"field": "project_pk", "value": pk}} for pk in project_pks]
    return terms[0] if len(terms) == 1 else {"boolean": {"should": terms}}


def compile_search(fieldset: FieldSet, query: SearchQuery) -> CompiledSearch:
    must: list[dict] = [project_clause(fieldset.project_pks)]
    if query.queries:
        qs = [query_string_to_json(q, fieldset) for q in query.queries.values()]
        must.append(qs[0] if len(qs) == 1 else {"boolean": {"should": qs}})
    sql_clauses: list[sql.Composable] = []
    if query.filters:
        compiled = compile_filters(query.filters, fieldset)
        must.extend(compiled.json_clauses)
        sql_clauses.extend(compiled.sql_clauses)
    params: list[Any] = []
    if query.ids:
        sql_clauses.append(sql.SQL("documents.doc_id = ANY(%s)"))
        params.append(list(query.ids))
    json_query = must[0] if len(must) == 1 else {"boolean": {"must": must}}
    where = sql.SQL(" AND ").join([sql.SQL("documents.id @@@ %s::jsonb"), *sql_clauses])
    return CompiledSearch(json_query, where, [Jsonb(json_query), *params])


@dataclass
class SearchResult:
    total: int
    results: list[dict]


def _coalesce(fs: list[FieldInfo]) -> sql.Composable:
    exprs = [field_sql(f) for f in fs]
    return exprs[0] if len(exprs) == 1 else sql.SQL("coalesce({})").format(sql.SQL(", ").join(exprs))


def order_by(fieldset: FieldSet, sort: list[tuple[str, Literal["asc", "desc"]]] | None, scored: bool) -> sql.Composable:
    items: list[sql.Composable] = []
    for name, order in sort or []:
        direction = sql.SQL("DESC NULLS LAST" if order == "desc" else "ASC NULLS LAST")
        if name == "_score":
            items.append(sql.SQL("paradedb.score(documents.id) {}").format(direction))
        elif name == "?":
            items.append(sql.SQL("random()"))
        else:
            fs = fieldset.by_name[name]
            if all(f.primary_date for f in fs):
                # sort_date is a real column, which pg_search can use for a fast Top-K scan
                items.append(sql.SQL("documents.sort_date {}").format(direction))
            else:
                items.append(sql.SQL("{} {}").format(_coalesce(fs), direction))
    if not items and scored:
        items.append(sql.SQL("paradedb.score(documents.id) DESC"))
    items.append(sql.SQL("documents.id"))
    return sql.SQL(", ").join(items)


async def count(conn: AsyncConnection, fieldset: FieldSet, query: SearchQuery) -> int:
    c = compile_search(fieldset, query)
    cur = await conn.execute(sql.SQL("SELECT count(*) AS n FROM documents WHERE {}").format(c.where), c.params)
    row = await cur.fetchone()
    return row["n"]  # type: ignore[index, call-overload]


async def search(
    conn: AsyncConnection,
    fieldset: FieldSet,
    query: SearchQuery,
    fields: list[str],
    *,
    sort: list[tuple[str, Literal["asc", "desc"]]] | None = None,
    page: int = 0,
    per_page: int = 10,
    snippets: dict[str, SnippetParams] | None = None,
    highlight: bool = False,
    with_total: bool = True,
) -> SearchResult:
    """
    Search documents, returning the given fields (and snippets for the fields in snippets).
    Access control on which fields may be returned (or only as snippets) is the responsibility of the caller.
    """
    c = compile_search(fieldset, query)
    scored = bool(query.queries)
    snippets = snippets or {}

    columns: list[sql.Composable] = [sql.SQL("documents.doc_id"), sql.SQL("documents.project_pk")]
    for name in dict.fromkeys([*fields, *snippets.keys()]):
        if name not in fieldset.by_name:
            raise QueryError(f"Unknown field: {name}")
        for f in fieldset.by_name[name]:
            columns.append(sql.SQL("{}->{} AS {}").format(sql.Identifier(f.column), sql.Literal(f.key), sql.Identifier(f.key)))
            if scored and f.type == "text" and (name in snippets or highlight):
                columns.append(
                    sql.SQL("paradedb.snippet_positions({}->{}) AS {}").format(
                        sql.Identifier(f.column), sql.Literal(f.key), sql.Identifier("_pos_" + f.key)
                    )
                )
    if scored:
        columns.append(sql.SQL("paradedb.score(documents.id) AS _score"))

    stmt = sql.SQL("SELECT {} FROM documents WHERE {} ORDER BY {} LIMIT %s OFFSET %s").format(
        sql.SQL(", ").join(columns), c.where, order_by(fieldset, sort, scored)
    )
    cur = await conn.execute(stmt, [*c.params, per_page, page * per_page])
    rows = await cur.fetchall()

    results = []
    for row in rows:
        project_fields = fieldset.project_fields[row["project_pk"]]  # type: ignore[index, call-overload]
        doc: dict[str, Any] = {"_id": row["doc_id"]}  # type: ignore[index, call-overload]
        for name in dict.fromkeys([*fields, *snippets.keys()]):
            f = project_fields.get(name)
            if f is None:
                continue
            value = row[f.key]  # type: ignore[index, call-overload]
            positions = byte_to_char_positions(value, row.get("_pos_" + f.key))  # type: ignore[union-attr]
            if name in snippets:
                value = make_snippet(value, positions, snippets[name], *(("<em>", "</em>") if highlight else ("", "")))
            elif highlight and positions:
                value = highlight_text(value, positions)
            if value is not None:
                doc[name] = value
        results.append(doc)

    total = await count(conn, fieldset, query) if with_total else len(results)
    return SearchResult(total=total, results=results)
