"""
Tests for the MCP (Model Context Protocol) endpoint at /mcp.

The MCP server runs with stateless_http=True and json_response=True, so every
POST to /mcp is an independent JSON-RPC exchange (no initialize handshake or
Mcp-Session-Id needed) and the response body is a single JSON-RPC message.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from amcat4 import api
from amcat4.config import AuthOptions
from amcat4.mcp.server import mcp
from amcat4.models import ApiKeyRestrictions, Roles
from amcat4.systemdata.apikeys import create_api_key, delete_api_key
from amcat4.systemdata.roles import create_project_role
from tests.tools import set_auth

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


@pytest.fixture(scope="session")
async def mcp_lifespan():
    # ASGITransport does not run the app lifespan; run the session manager here.
    # session_manager.run() may only be entered once per process, hence session scope.
    async with mcp.session_manager.run():
        yield


@pytest.fixture(scope="session")
async def mcp_client(mcp_lifespan):
    # Plain client (not the CSRF-injecting conftest client): MCP requests are
    # header-authenticated and never carry a session cookie.
    async with AsyncClient(transport=ASGITransport(app=api.app), base_url="http://test") as client:
        yield client


async def mcp_post(client: AsyncClient, method: str, params: dict, api_key: str | None = None, headers: dict | None = None):
    _headers = dict(MCP_HEADERS)
    if api_key:
        _headers["X-API-Key"] = api_key
    if headers:
        _headers.update(headers)
    return await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        headers=_headers,
    )


async def call_tool(
    client: AsyncClient, name: str, arguments: dict | None = None, api_key: str | None = None, headers: dict | None = None
) -> tuple[bool, Any]:
    """Call an MCP tool, returning (is_error, unwrapped content)."""
    response = await mcp_post(
        client, "tools/call", {"name": name, "arguments": arguments or {}}, api_key=api_key, headers=headers
    )
    assert response.status_code == 200, f"tools/call {name} returned HTTP {response.status_code}: {response.text}"
    message = response.json()
    assert "result" in message, f"tools/call {name} returned JSON-RPC error: {message}"
    result = message["result"]
    if result.get("isError"):
        return True, "\n".join(block.get("text", "") for block in result["content"])
    structured = result.get("structuredContent")
    if structured is not None:
        # FastMCP wraps non-object results (lists, scalars) in {"result": ...}
        if set(structured.keys()) == {"result"}:
            return False, structured["result"]
        return False, structured
    return False, result.get("content")


@pytest.fixture(scope="function")
async def admin_api_key(admin, index_docs):
    # Explicit project role: query/aggregate role checks (unlike write-role checks) do not
    # elevate for a global server-ADMIN role, so grant it directly to get real READER+ access
    # rather than tests silently degrading to zero-field results.
    await create_project_role(admin, index_docs, Roles.ADMIN)
    id, key = await create_api_key(admin, "mcp_test_key", datetime(2035, 1, 1, tzinfo=UTC), ApiKeyRestrictions())
    yield key
    await delete_api_key(id)


@pytest.mark.anyio
async def test_mcp_requires_key_for_authenticated_guests(mcp_client):
    with set_auth(AuthOptions.allow_authenticated_guests):
        response = await mcp_post(mcp_client, "tools/list", {})
        assert response.status_code == 401
        assert "X-API-Key" in response.json()["detail"]
        assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.anyio
async def test_mcp_guest_access(mcp_client, index_docs, index_many):
    # default auth mode is allow_guests: keyless requests act as anonymous guests
    response = await mcp_post(mcp_client, "tools/list", {})
    assert response.status_code == 200

    # index_many has guest role READER, so a keyless query succeeds
    is_error, result = await call_tool(mcp_client, "query_documents", {"index": index_many})
    assert not is_error
    assert result["meta"]["total_count"] == 20

    # index_docs has no guest role, so guests get exactly their REST permissions: no field
    # content (only _id and the total_count metadata), same as a direct REST call would.
    is_error, result = await call_tool(mcp_client, "query_documents", {"index": index_docs})
    assert not is_error
    assert all(set(doc.keys()) == {"_id"} for doc in result["results"])


@pytest.mark.anyio
async def test_mcp_no_auth_mode(mcp_client):
    with set_auth(AuthOptions.no_auth):
        response = await mcp_post(mcp_client, "tools/list", {})
        assert response.status_code == 200
        tools = {tool["name"] for tool in response.json()["result"]["tools"]}
        assert tools >= {"list_indices", "query_documents", "update_document", "create_field", "get_document", "list_fields"}


@pytest.mark.anyio
async def test_bearer_header_accepted(mcp_client, index_docs, admin_api_key):
    # Authorization: Bearer must work as an alias for X-API-Key; a successful,
    # permission-checked call also proves the ContextVar propagates through the
    # session manager's task group. get_index requires (at least) OBSERVER role,
    # which the admin's server-level ADMIN role satisfies.
    is_error, result = await call_tool(
        mcp_client, "get_index", {"index": index_docs}, headers={"Authorization": f"Bearer {admin_api_key}"}
    )
    assert not is_error
    assert result["id"] == index_docs


@pytest.mark.anyio
async def test_query_documents(mcp_client, index_docs, admin_api_key):
    is_error, result = await call_tool(
        mcp_client,
        "query_documents",
        {"index": index_docs, "queries": "test", "per_page": 5},
        api_key=admin_api_key,
    )
    assert not is_error
    assert len(result["results"]) > 0
    assert all("_id" in doc and "text" in doc for doc in result["results"])


@pytest.mark.anyio
async def test_annotation_roundtrip(mcp_client, index_docs, admin_api_key):
    # The core user workflow: create an annotation field, set it on a document, read it back
    is_error, result = await call_tool(
        mcp_client, "create_field", {"index": index_docs, "fields": {"sentiment": "keyword"}}, api_key=admin_api_key
    )
    assert not is_error, result

    is_error, result = await call_tool(
        mcp_client,
        "update_document",
        {"index": index_docs, "doc_id": "0", "fields": {"sentiment": "positive"}},
        api_key=admin_api_key,
    )
    assert not is_error, result
    assert result["status"] == "updated"

    is_error, result = await call_tool(mcp_client, "get_document", {"index": index_docs, "doc_id": "0"}, api_key=admin_api_key)
    assert not is_error, result
    assert result["sentiment"] == "positive"


@pytest.mark.anyio
async def test_role_enforcement(mcp_client, index_docs, admin):
    # API-key restrictions act as a role ceiling: METAREADER cannot write
    id, key = await create_api_key(
        admin,
        "mcp_restricted_key",
        datetime(2035, 1, 1, tzinfo=UTC),
        ApiKeyRestrictions(project_roles={index_docs: "METAREADER"}),
    )
    try:
        is_error, result = await call_tool(
            mcp_client,
            "update_document",
            {"index": index_docs, "doc_id": "0", "fields": {"cat": "c"}},
            api_key=key,
        )
        assert is_error
        assert "403" in result or "permission" in result.lower()
    finally:
        await delete_api_key(id)


@pytest.mark.anyio
async def test_list_fields_and_values(mcp_client, index_docs, admin_api_key):
    is_error, result = await call_tool(mcp_client, "list_fields", {"index": index_docs}, api_key=admin_api_key)
    assert not is_error
    assert result["cat"]["type"] == "keyword"

    is_error, result = await call_tool(
        mcp_client, "get_field_values", {"index": index_docs, "field": "cat"}, api_key=admin_api_key
    )
    assert not is_error
    assert set(result) == {"a", "b"}
