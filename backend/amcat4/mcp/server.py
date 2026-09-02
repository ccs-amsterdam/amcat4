"""
FastMCP server exposing AmCAT4 query and annotation tools.

Docstrings of the tool functions are shown to the LLM client; they document
parameter shapes (queries, filters) and the annotation workflow. Every tool
forwards to the REST API in-process (see client.py), so roles and API-key
restrictions are enforced by the existing endpoints.
"""

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from amcat4.mcp.client import api_request

mcp = FastMCP(
    "AmCAT4",
    instructions=(
        "Tools for querying and annotating documents on an AmCAT4 text-analysis server. "
        "Typical annotation workflow: list_indices -> list_fields -> query_documents "
        "-> create_field (once, e.g. type 'keyword' or 'tag') -> update_document per document."
    ),
    stateless_http=True,
    json_response=True,
    # FastMCP defaults to host="127.0.0.1", which auto-enables DNS-rebinding Host-header
    # validation that only allows localhost/127.0.0.1. We're mounted behind Caddy under the
    # server's real hostname, so that default would 421 every real request. We rely on the
    # same auth (API key / role checks, forwarded to the REST API) as the rest of the app
    # instead, so this protection is both wrong here and redundant.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@mcp.tool()
async def list_indices() -> list[dict[str, Any]]:
    """
    List the indices (document collections) on this AmCAT server that the current
    user can access. Returns id, name, user_role, description, and folder per index.
    Use the 'id' as the 'index' argument of the other tools.
    """
    response = await api_request("GET", "/api/index")
    return [{key: ix.get(key) for key in ("id", "name", "user_role", "description", "folder")} for ix in response.json()]


@mcp.tool()
async def get_index(index: str) -> dict[str, Any]:
    """
    Get details of a single index: name, description, user_role, guest_role,
    contact info, and size in bytes.
    """
    response = await api_request("GET", f"/api/index/{index}")
    return response.json()


@mcp.tool()
async def list_fields(index: str) -> dict[str, Any]:
    """
    List the fields (columns) of an index, with their types (e.g. text, keyword,
    date, integer, tag). Use this to learn which fields can be queried, filtered,
    aggregated, or updated.
    """
    response = await api_request("GET", f"/api/index/{index}/fields")
    return response.json()


@mcp.tool()
async def get_field_values(index: str, field: str) -> list[Any]:
    """
    Get the unique values of a field (e.g. the labels used in a keyword or tag
    field). Errors if the field has more than 2000 unique values.
    """
    response = await api_request("GET", f"/api/index/{index}/fields/{field}/values")
    return response.json()


@mcp.tool()
async def get_field_stats(index: str, field: str) -> dict[str, Any]:
    """
    Get statistics (min, max, avg, count) for a numeric or date field.
    """
    response = await api_request("GET", f"/api/index/{index}/fields/{field}/stats")
    return response.json()


@mcp.tool()
async def query_documents(
    index: str,
    queries: str | list[str] | dict[str, str] | None = None,
    fields: list[str] | None = None,
    filters: dict[str, Any] | None = None,
    sort: str | list[str] | list[dict[str, Any]] | None = None,
    per_page: int = 10,
    page: int = 0,
    highlight: bool = False,
) -> dict[str, Any]:
    """
    Query documents in an index (or several indices: pass ids comma-separated).
    Returns {"results": [documents with their _id], "meta": {"total_count", "page",
    "page_count"}}. The '_id' of each result is the doc_id for get_document /
    update_document. Increase 'page' to paginate.

    - queries: full-text search using Elasticsearch query string syntax
      (supports AND/OR/NOT, "exact phrases", wildcard*). Either a single query
      string, a list of query strings, or a dict mapping labels to query strings.
    - filters: filter on field values. Dict mapping field names to either a list
      of values for exact matches (e.g. {"cat": ["a", "b"]}) or a range/spec dict
      with keys 'values', 'gt', 'gte', 'lt', 'lte', 'exists'
      (e.g. {"date": {"gte": "2023-01-01"}}).
    - fields: which document fields to return (default: all the user may read).
    - sort: field name, list of field names, or [{"field": {"order": "desc"}}].
      Use "?" for random order.
    - highlight: if true, matched terms are wrapped in <em> tags.
    """
    body = {
        "queries": queries,
        "fields": fields,
        "filters": filters,
        "sort": sort,
        "per_page": max(1, min(per_page, 200)),
        "page": page,
        "highlight": highlight,
    }
    response = await api_request("POST", f"/api/index/{index}/query", json=body)
    return response.json()


@mcp.tool()
async def aggregate_documents(
    index: str,
    axes: list[dict[str, Any]] | None = None,
    aggregations: list[dict[str, Any]] | None = None,
    queries: str | list[str] | dict[str, str] | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Aggregate documents in an index (count and/or compute statistics per group),
    e.g. number of documents per category or per month.

    - axes: what to group by, as a list of {"field": name} dicts; date fields
      also take an "interval" (e.g. {"field": "date", "interval": "month"}).
      Omit for a global aggregation.
    - aggregations: statistics to compute, as a list of {"field": name,
      "function": one of "avg"/"min"/"max"/"sum"} dicts. Omit to just count
      documents (n).
    - queries/filters: same shapes as in query_documents.
    """
    body = {
        "axes": axes,
        "aggregations": aggregations,
        "queries": queries,
        "filters": filters,
    }
    response = await api_request("POST", f"/api/index/{index}/aggregate", json=body)
    return response.json()


@mcp.tool()
async def get_document(index: str, doc_id: str, fields: list[str] | None = None) -> dict[str, Any]:
    """
    Get a single document by id (the '_id' from query_documents results).
    Optionally restrict which fields are returned.
    """
    params = {"fields": ",".join(fields)} if fields else None
    response = await api_request("GET", f"/api/index/{index}/documents/{doc_id}", params=params)
    return response.json()


@mcp.tool()
async def update_document(index: str, doc_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    """
    Partially update a document: the given fields are set, other fields are left
    unchanged. This is the tool for writing annotations back per document, e.g.
    fields={"sentiment": "positive"} after create_field created 'sentiment'.
    doc_id is the '_id' from query_documents results. Requires WRITER role.
    """
    await api_request("PUT", f"/api/index/{index}/documents/{doc_id}", json=fields)
    return {"status": "updated", "doc_id": doc_id}


@mcp.tool()
async def create_field(index: str, fields: dict[str, str]) -> dict[str, Any]:
    """
    Create one or more fields in an index, as a dict mapping field name to type
    ({"sentiment": "keyword"}). Valid types: text, date, boolean, keyword, number,
    integer, object, vector, geo_point, image, video, audio, tag, url.
    For annotations, use 'keyword' for a single label per document or 'tag' for
    multiple labels per document. Requires WRITER role.
    """
    await api_request("POST", f"/api/index/{index}/fields", json=fields)
    return {"status": "created", "fields": fields}


@mcp.tool()
async def update_documents_by_query(
    index: str,
    field: str,
    value: str | int | float | None,
    queries: str | list[str] | dict[str, str] | None = None,
    filters: dict[str, Any] | None = None,
    ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Set one field to one value on all documents matching a query, filters, and/or
    a list of document ids (same shapes as in query_documents) — bulk annotation
    in a single call. Returns the number of updated documents. Requires WRITER role.
    """
    body = {"field": field, "value": value, "queries": queries, "filters": filters, "ids": ids}
    response = await api_request("POST", f"/api/index/{index}/update_by_query", json=body)
    return response.json()


@mcp.tool()
async def update_tags(
    index: str,
    action: Literal["add", "remove"],
    field: str,
    tag: str,
    queries: str | list[str] | dict[str, str] | None = None,
    filters: dict[str, Any] | None = None,
    ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Add or remove a tag on all documents matching a query, filters, and/or a list
    of document ids (same shapes as in query_documents). The field must be of type
    'tag' (create it with create_field first). Returns the number of updated
    documents. Requires WRITER role.
    """
    body = {"action": action, "field": field, "tag": tag, "queries": queries, "filters": filters, "ids": ids}
    response = await api_request("POST", f"/api/index/{index}/tags_update", json=body)
    return response.json()
