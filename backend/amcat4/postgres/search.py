"""
Searching documents in the postgres backend.

A search is a single SQL query on the documents table. Everything that can be expressed as a pg_search query
(project selection, query string, most filters) is combined into one json query, so it is evaluated inside the
BM25 index. Remaining conditions are added as plain SQL.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from psycopg import AsyncConnection, sql
from psycopg.types.json import Jsonb

from amcat4.models import FilterSpec, SnippetParams
from amcat4.postgres.fields import FieldInfo, FieldSet, QueryError
from amcat4.postgres.filters import compile_filters, field_sql
from amcat4.postgres.querystring import highlight_patterns, match_positions, parse_query, query_string_to_json
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


def _compile_query_string(label: str, q: str, fieldset: FieldSet) -> dict:
    try:
        return query_string_to_json(q, fieldset)
    except QueryError as e:
        where = f"query {q!r}" if label == q else f"query {label!r} ({q!r})"
        raise QueryError(f"Error in {where}: {e}") from e


def compile_search(fieldset: FieldSet, query: SearchQuery) -> CompiledSearch:
    must: list[dict] = [project_clause(fieldset.project_pks)]
    if query.queries:
        qs = [_compile_query_string(label, q, fieldset) for label, q in query.queries.items()]
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
    last_id: int | None = None  # internal id of the last result, for keyset pagination


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
        elif name == "_id":
            items.append(sql.SQL("documents.doc_id {}").format(direction))
        else:
            if name not in fieldset.by_name:
                raise QueryError(f"Cannot sort on unknown field: {name}")
            fs = fieldset.by_name[name]
            sort_columns = {f.sort_column for f in fs}
            if len(sort_columns) == 1 and None not in sort_columns:
                # the field is in a sort slot: a real column, which pg_search can use for a fast Top-K scan
                items.append(sql.SQL("documents.{} {}").format(sql.Identifier(fs[0].sort_column), direction))  # type: ignore[arg-type]
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
    keyset: bool = False,
    after_id: int | None = None,
    offset: int | None = None,
    similar: tuple[str, list[float]] | None = None,
) -> SearchResult:
    """
    Search documents, returning the given fields (and snippets for the fields in snippets).
    Access control on which fields may be returned (or only as snippets) is the responsibility of the caller.

    If keyset is True, results are ordered by internal id and only results after after_id are returned
    (efficient pagination through large result sets; sort and page are ignored).
    offset overrides page * per_page.
    similar: (vector field, vector): order by cosine distance to the vector (documents without vector are skipped)
    """
    from amcat4.postgres.documents import field_select

    c = compile_search(fieldset, query)
    scored = bool(query.queries)
    snippets = snippets or {}

    columns: list[sql.Composable] = [sql.SQL("documents.doc_id"), sql.SQL("documents.project_pk")]
    # fields that do not exist (in any of the projects) are simply not returned
    fields = [name for name in fields if name in fieldset.by_name]
    snippets = {name: s for name, s in snippets.items() if name in fieldset.by_name}
    for name in dict.fromkeys([*fields, *snippets.keys()]):
        for f in fieldset.by_name[name]:
            columns.append(sql.SQL("{} AS {}").format(field_select(f), sql.Identifier(f.key)))
            if scored and f.type == "text" and (name in snippets or highlight):
                columns.append(
                    sql.SQL("paradedb.snippet_positions({}->{}) AS {}").format(
                        sql.Identifier(f.column), sql.Literal(f.key), sql.Identifier("_pos_" + f.key)
                    )
                )
    if scored:
        columns.append(sql.SQL("paradedb.score(documents.id) AS _score"))
    columns.append(sql.SQL("documents.id AS _internal_id"))

    where, params = c.where, list(c.params)
    join: sql.Composable = sql.SQL("")
    if similar:
        vfield, vector = similar
        vfs = fieldset.by_name.get(vfield)
        if not vfs or vfs[0].type != "vector":
            raise QueryError(f"{vfield} is not a vector field")
        join = sql.SQL("JOIN document_vectors sim ON sim.document_id = documents.id AND sim.field_pk = ANY({})").format(
            sql.Literal([f.pk for f in vfs])
        )
        columns.append(
            sql.SQL("1 - (sim.embedding <=> {}::public.vector) AS _similarity").format(sql.Literal(json.dumps(vector)))
        )
    if keyset:
        if after_id is not None:
            where = sql.SQL("{} AND documents.id > %s").format(where)
            params.append(after_id)
        ordering: sql.Composable = sql.SQL("documents.id")
        offset = 0
    elif similar:
        ordering = sql.SQL("_similarity DESC, documents.id")
        offset = page * per_page if offset is None else offset
    else:
        ordering = order_by(fieldset, sort, scored)
        offset = page * per_page if offset is None else offset
    stmt = sql.SQL("SELECT {} FROM documents {} WHERE {} ORDER BY {} LIMIT %s OFFSET %s").format(
        sql.SQL(", ").join(columns), join, where, ordering
    )
    cur = await conn.execute(stmt, [*params, per_page, offset])
    rows = await cur.fetchall()

    # Patterns to find query matches for highlighting / snippets (combined with the positions reported by pg_search,
    # which does not report positions for all query types)
    nodes = [parse_query(q) for q in (query.queries or {}).values()]
    default_names = {f.name for f in fieldset.default_fields()}
    patterns = {
        name: [p for node in nodes for p in highlight_patterns(node, name, name in default_names)]
        for name in dict.fromkeys([*fields, *snippets.keys()])
    }

    results = []
    for row in rows:
        project_fields = fieldset.project_fields[row["project_pk"]]  # type: ignore[index, call-overload]
        doc: dict[str, Any] = {"_id": row["doc_id"]}  # type: ignore[index, call-overload]
        for name in dict.fromkeys([*fields, *snippets.keys()]):
            f = project_fields.get(name)
            if f is None:
                continue
            value = row[f.key]  # type: ignore[index, call-overload]
            positions = None
            if isinstance(value, str) and nodes and (name in snippets or highlight):
                positions = byte_to_char_positions(value, row.get("_pos_" + f.key)) or []  # type: ignore[union-attr]
                positions = _merge_positions(positions + match_positions(value, patterns[name]))
            if name in snippets:
                value = make_snippet(value, positions, snippets[name], *(("<em>", "</em>") if highlight else ("", "")))
            elif highlight and positions:
                value = highlight_text(value, positions)
            if value is not None:
                doc[name] = value
        if similar:
            doc["_similarity"] = row["_similarity"]  # type: ignore[index, call-overload]
        results.append(doc)

    total = await count(conn, fieldset, query) if with_total else len(results)
    last_id = rows[-1]["_internal_id"] if rows else None  # type: ignore[index, call-overload]
    return SearchResult(total=total, results=results, last_id=last_id)


def _merge_positions(positions: list[list[int]]) -> list[list[int]]:
    """Sort and merge overlapping (start, end) positions"""
    merged: list[list[int]] = []
    for start, end in sorted((p[0], p[1]) for p in positions):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged
