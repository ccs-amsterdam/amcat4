"""
All things query
"""

import logging
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any, Literal, Union

from psycopg.types.json import Jsonb

from amcat4.models import CreateDocumentField, FieldSpec, FieldType, FilterSpec, SnippetParams, SortSpec
from amcat4.postgres import documents as storage
from amcat4.postgres.connection import connection, fetch_one
from amcat4.postgres.fields import FieldSet
from amcat4.postgres.projects import project_pk
from amcat4.postgres.search import SearchQuery, compile_search, search
from amcat4.systemdata.fields import create_fields, create_or_verify_tag_field, field_infos, get_fieldset, list_fields


class QueryResult:
    def __init__(
        self,
        data: list[dict],
        n: int | None = None,
        per_page: int | None = None,
        page: int | None = None,
        page_count: int | None = None,
        scroll_id: str | None = None,
    ):
        if n and (page_count is None) and (per_page is not None):
            page_count = ceil(n / per_page)
        self.data = data
        self.total_count = n
        self.page = page
        self.page_count = page_count
        self.per_page = per_page
        self.scroll_id = scroll_id

    def as_dict(self) -> dict:
        meta: dict[str, int | str | None] = {
            "total_count": self.total_count,
            "per_page": self.per_page,
            "page_count": self.page_count,
        }
        if self.scroll_id:
            meta["scroll_id"] = self.scroll_id
        else:
            meta["page"] = self.page
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


def _parse_duration(scroll: str | bool | None) -> timedelta:
    """Parse an elastic-style duration (e.g. 2m, 30s, 1h) for keeping scroll contexts alive"""
    if not scroll or scroll is True:
        return timedelta(minutes=2)
    m = re.fullmatch(r"(\d+)\s*([smhd]?)", str(scroll).strip())
    if not m:
        raise ValueError(f"Invalid scroll duration: {scroll}")
    unit = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days", "": "seconds"}[m.group(2)]
    return timedelta(**{unit: int(m.group(1))})


async def query_documents(
    index: Union[str, list[str]],
    fields: list[FieldSpec] | None = None,
    queries: dict[str, str] | None = None,
    filters: dict[str, FilterSpec] | None = None,
    sort: list[dict[str, SortSpec]] | None = None,
    *,
    page: int = 0,
    per_page: int = 10,
    scroll=None,
    scroll_id: str | None = None,
    highlight: bool = False,
    **kwargs,
) -> QueryResult | None:
    """
    Conduct a query, returning the found documents.

    It will return at most per_page results.
    In normal (paginated) mode, the next batch can be requested by incrementing the page parameter.
    If the scroll parameter is given, the result will contain a scroll_id which can be used to get the next batch.
    In case there are no more documents to scroll, it will return None
    :param index: The name of the index or indexes
    :param fields: List of fields using the FieldSpec syntax. If not specified, only return _id.
                   !We require the fields to be specified for security reasons.
                   !Any logic for determining whether a user can see the field should be done in the API layer.
    :param queries: if not None, a dict with labels and queries {label1: query1, ...}
    :param filters: if not None, a dict where the key is the field and the value is a FilterSpec
    :param page: The number of the page to request (starting from zero)
    :param per_page: The number of hits per page
    :param scroll: if not None, will create a scroll context rather than a paginated request. Parameter should
                   specify the time the context should be kept alive, or True to get the default of 2m.
    :param scroll_id: if not None, should be a previously returned scroll_id to retrieve a new page of results
    :param highlight: if True, add <em> tags to query matches in fields
    :param sort: Sort order of results, a list of {field: SortSpec} dicts. Use "?" as field for random order.
    :return: a QueryResult, or None if there is no scroll result anymore
    """
    if fields is not None and not isinstance(fields, list):
        raise ValueError("fields should be a list")

    if scroll_id:
        return await _continue_scroll(scroll_id)

    indices = [index] if isinstance(index, str) else index
    params: dict[str, Any] = dict(
        indices=indices,
        fields=[f.model_dump() for f in fields or []],
        queries=queries,
        filters={k: v.model_dump(exclude_none=True) for k, v in (filters or {}).items()},
        sort=_sort_spec(sort),
        per_page=per_page,
        highlight=highlight,
    )
    if not scroll:
        result, _ = await _run_query(params, page=page)
        return QueryResult(result.results, n=result.total, per_page=per_page, page=page)

    # Scroll: store the query server side, and return the first batch
    sid = secrets.token_urlsafe(24)
    expires = datetime.now(UTC) + _parse_duration(scroll)
    params["scroll"] = str(scroll)
    async with connection() as conn:
        await conn.execute("DELETE FROM scrolls WHERE expires_at < now()")
        await conn.execute("INSERT INTO scrolls (id, params, expires_at) VALUES (%s, %s, %s)", [sid, Jsonb(params), expires])
    return await _continue_scroll(sid)


async def _run_query(params: dict, page: int = 0, after_id: int | None = None, keyset: bool = False):
    fieldset = await get_fieldset(params["indices"])
    fields = [FieldSpec.model_validate(f) for f in params["fields"]]
    filters = {k: FilterSpec.model_validate(v) for k, v in (params.get("filters") or {}).items()}
    snippets: dict[str, SnippetParams] = {f.name: f.snippet for f in fields if f.snippet is not None}
    names = [f.name for f in fields if f.snippet is None]
    async with connection() as conn:
        result = await search(
            conn,
            fieldset,
            _search_query(params.get("queries"), filters),
            names,
            sort=params.get("sort"),
            page=page,
            per_page=params["per_page"],
            snippets=snippets,
            highlight=params.get("highlight", False),
            keyset=keyset,
            after_id=after_id,
        )
    return result, fieldset


async def _continue_scroll(scroll_id: str) -> QueryResult | None:
    row = await fetch_one("SELECT params, position, page FROM scrolls WHERE id = %s AND expires_at > now()", [scroll_id])
    if row is None:
        return None
    params = row["params"]
    # Unsorted scrolls use (efficient) keyset pagination on the internal id, sorted scrolls use pages
    keyset = not params.get("sort")
    result, _ = await _run_query(params, page=row["page"], after_id=row["position"], keyset=keyset)
    if not result.results:
        async with connection() as conn:
            await conn.execute("DELETE FROM scrolls WHERE id = %s", [scroll_id])
        return None
    expires = datetime.now(UTC) + _parse_duration(params.get("scroll"))
    async with connection() as conn:
        await conn.execute(
            "UPDATE scrolls SET position = %s, page = page + 1, expires_at = %s WHERE id = %s",
            [result.last_id, expires, scroll_id],
        )
    return QueryResult(result.results, n=result.total, per_page=params["per_page"], scroll_id=scroll_id)


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


# Results of finished reindex 'tasks'. Reindexing runs synchronously, but we keep the task interface
_TASKS: dict[str, dict] = {}


async def reindex(
    source_index: str,
    destination_index: str,
    queries: dict[str, str] | None = None,
    filters: dict[str, FilterSpec] | None = None,
    field_options: dict[str, dict] | None = None,
    wait_for_completion=False,
):
    """Copy documents (optionally selected by queries/filters) to another index.
    This will first create any fields missing in the destination index. Returns a {'task': task_id} dict
    (the copy is done when this function returns, but the task can be used to get the status)

    field_options: per-field options dict keyed by source field name, each with optional keys:
      - rename: str — copy field under this new name in destination
      - exclude: bool — if True, skip this field entirely
      - type: FieldType — override amcat type for fields new to destination
    """
    from_pk = await project_pk(source_index)
    try:
        to_pk = await project_pk(destination_index)
    except Exception:
        raise Exception("Please create index before re-indexing!")

    field_options = field_options or {}
    dest_fields = await list_fields(destination_index)
    source_field_defs = await list_fields(source_index)

    # Sync fields to destination, applying renames, exclusions, and type overrides
    new_fields: dict[str, CreateDocumentField] = {}
    mapping: dict[str, str] = {}
    for field, definition in source_field_defs.items():
        opts = field_options.get(field, {})
        if opts.get("exclude"):
            continue
        dest_name = opts.get("rename") or field
        mapping[field] = dest_name
        if dest_name in dest_fields:
            continue
        type_override: FieldType | None = opts.get("type")
        if type_override:
            new_fields[dest_name] = CreateDocumentField(type=type_override)
        else:
            new_fields[dest_name] = CreateDocumentField(
                type=definition.type,
                elastic_type=definition.elastic_type,
                identifier=definition.identifier,
                metareader=definition.metareader,
                client_settings=definition.client_settings,
            )

    if new_fields:
        logging.info(f"Creating fields {list(new_fields)}")
        await create_fields(destination_index, new_fields)

    source_infos = await field_infos(source_index)
    dest_infos = await field_infos(destination_index)
    field_map = {source_infos[s]: dest_infos[d] for s, d in mapping.items()}

    fieldset = FieldSet({from_pk: source_infos})
    c = compile_search(fieldset, _search_query(queries, filters))
    async with connection() as conn:
        n = await storage.copy_documents(conn, from_pk, to_pk, field_map, c.where, c.params)

    task_id = f"reindex-{uuid.uuid4().hex}"
    _TASKS[task_id] = {"completed": True, "task": task_id, "response": {"total": n, "created": n}}
    return {"task": task_id, "total": n}


async def get_task_status(task_id):
    if task_id not in _TASKS:
        raise ValueError(f"Unknown task {task_id}")
    return _TASKS[task_id]
