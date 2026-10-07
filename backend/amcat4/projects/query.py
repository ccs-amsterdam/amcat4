"""
All things query
"""

import base64
import json
from math import ceil
from typing import Any, Literal, Union

from amcat4.models import FieldSpec, FilterSpec, SnippetParams, SortSpec
from amcat4.postgres import documents as storage
from amcat4.postgres.connection import connection
from amcat4.postgres.search import SearchQuery, search
from amcat4.systemdata.fields import create_or_verify_tag_field, get_fieldset


class QueryResult:
    def __init__(
        self,
        data: list[dict],
        n: int | None = None,
        per_page: int | None = None,
        page: int | None = None,
        next: str | None = None,
    ):
        self.data = data
        self.total_count = n
        self.page = page
        self.page_count = ceil(n / per_page) if n is not None and per_page else None
        self.per_page = per_page
        self.next = next

    def as_dict(self) -> dict:
        meta = {
            "total_count": self.total_count,
            "per_page": self.per_page,
            "page_count": self.page_count,
            "page": self.page,
            "next": self.next,
        }
        return dict(meta=meta, results=self.data)


def _search_query(queries, filters, ids=None) -> SearchQuery:
    return SearchQuery(queries=queries or None, filters=filters or None, ids=list(ids) if ids else None)


def _sort_spec(sort: list[dict[str, SortSpec]] | None) -> list[tuple[str, Literal["asc", "desc"]]] | None:
    if not sort:
        return None
    out: list[tuple[str, Literal["asc", "desc"]]] = []
    for s in sort:
        for k, v in s.items():
            order = v.order if isinstance(v, SortSpec) else SortSpec.model_validate(v).order
            out.append((k, order))
    return out


def _encode_cursor(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).decode()


def _decode_cursor(cursor: str) -> dict:
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except Exception:
        raise ValueError(f"Invalid cursor: {cursor}")


async def query_documents(
    index: Union[str, list[str]],
    fields: list[FieldSpec] | None = None,
    queries: dict[str, str] | None = None,
    filters: dict[str, FilterSpec] | None = None,
    sort: list[dict[str, SortSpec]] | None = None,
    *,
    page: int = 0,
    per_page: int = 10,
    after: str | None = None,
    highlight: bool = False,
    similar: tuple[str, list[float]] | None = None,
    queryable: set[str] | None = None,
) -> QueryResult:
    """
    Conduct a query, returning the found documents.

    :param index: The id of the project, or a list of project ids
    :param fields: List of fields using the FieldSpec syntax. If not specified, only return _id.
                   !We require the fields to be specified for security reasons.
                   !Any logic for determining whether a user can see the field should be done in the API layer.
    :param queries: if not None, a dict with labels and queries {label1: query1, ...}
    :param filters: if not None, a dict where the key is the field and the value is a FilterSpec
    :param sort: Sort order of results, a list of {field: SortSpec} dicts. Use "?" as field for random order.
    :param page: The number of the page to request (starting from zero)
    :param per_page: The number of results per page
    :param after: A cursor (the 'next' value of a previous result) to get the next batch of results. This is the
                  efficient way to retrieve large result sets: without sort, results are then ordered by internal id,
                  which makes retrieving the next batch fast.
    :param highlight: if True, add <em> tags to query matches in fields
    :param similar: (vector field, vector): order results by (cosine) similarity to this vector
    :param queryable: the fields that may be used in queries and filters (None = all fields)
    """
    if fields is not None and not isinstance(fields, list):
        raise ValueError("fields should be a list")
    fieldset = await get_fieldset([index] if isinstance(index, str) else index, queryable=queryable)
    fields = fields or []
    snippets: dict[str, SnippetParams] = {f.name: f.snippet for f in fields if f.snippet is not None}
    names = [f.name for f in fields if f.snippet is None]
    sort_spec = _sort_spec(sort)

    cursor = _decode_cursor(after) if after else {}
    # Without explicit sort (and without query/similarity scores), cursors use keyset pagination on the internal id,
    # otherwise the cursor is an offset
    keyset = "id" in cursor
    offset = cursor.get("offset", page * per_page)

    async with connection() as conn:
        result = await search(
            conn,
            fieldset,
            _search_query(queries, filters),
            names,
            sort=sort_spec,
            page=0,
            offset=offset,
            per_page=per_page,
            snippets=snippets,
            highlight=highlight,
            keyset=keyset,
            after_id=cursor.get("id"),
            similar=similar,
        )
    next_cursor = None
    if len(result.results) == per_page:
        if keyset or (after is None and not sort_spec and not similar and not queries):
            next_cursor = _encode_cursor({"id": result.last_id})
        else:
            next_cursor = _encode_cursor({"offset": offset + per_page})
    return QueryResult(result.results, n=result.total, per_page=per_page, page=None if after else page, next=next_cursor)


async def update_tag_query(
    index: str | list[str],
    action: Literal["add", "remove"],
    field: str,
    tag: str,
    queries: dict[str, str] | None = None,
    filters: dict[str, FilterSpec] | None = None,
    ids: list[str] | None = None,
):
    """Add or remove tags using a query"""
    await create_or_verify_tag_field(index, field)
    fieldset = await get_fieldset(index)
    query = _search_query(queries, filters, ids)
    async with connection() as conn:
        from amcat4.postgres.search import count

        total = await count(conn, fieldset, query)
        updated = await storage.update_tag_by_query(conn, fieldset, query, field, tag, action)
    return dict(updated=updated, total=total)


async def update_query(
    index: str | list[str],
    field: str,
    value: Any,
    queries: dict[str, str] | None = None,
    filters: dict[str, FilterSpec] | None = None,
    ids: list[str] | None = None,
):
    fieldset = await get_fieldset(index)
    if field not in fieldset.by_name:
        raise ValueError(f"Field {field} does not exist")
    async with connection() as conn:
        updated = await storage.update_by_query(conn, fieldset, _search_query(queries, filters, ids), field, value)
    return dict(updated=updated, total=updated)


async def delete_query(
    index: str | list[str],
    queries: dict[str, str] | None = None,
    filters: dict[str, FilterSpec] | None = None,
    ids: list[str] | None = None,
):
    fieldset = await get_fieldset(index)
    async with connection() as conn:
        deleted = await storage.delete_by_query(conn, fieldset, _search_query(queries, filters, ids))
    return dict(updated=deleted, total=deleted)
