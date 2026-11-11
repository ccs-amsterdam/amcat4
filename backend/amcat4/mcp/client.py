"""
In-process REST client for MCP tools.

MCP tools do not call domain functions directly: that would bypass the
authentication and role checks in the REST endpoints. Instead, every tool
call is forwarded in-process to the existing REST API via an ASGI transport
(no network hop), carrying the caller's API key as X-API-Key. This way
`authenticated_user` and the role checks run exactly as for any HTTP client.
"""

from contextvars import ContextVar
from typing import Any

import httpx
from mcp.server.fastmcp.exceptions import ToolError

# The API key of the current MCP request, set by MCPAuthMiddleware (auth.py)
# and read when forwarding requests to the REST API. None means anonymous
# guest access (mirroring a REST request without credentials).
api_key_var: ContextVar[str | None] = ContextVar("amcat_mcp_api_key", default=None)

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        # Import here rather than at module level: amcat4.api mounts the MCP
        # server, so a module-level import would be circular.
        from amcat4 import api

        _client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api.app),
            base_url="http://amcat",
            timeout=30.0,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def api_request(
    method: str,
    path: str,
    *,
    json: Any = None,
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    """
    Forward a request to the REST API, raising ToolError on error responses.
    """
    headers = {}
    api_key = api_key_var.get()
    if api_key:
        headers["X-API-Key"] = api_key

    response = await get_client().request(method, path, json=json, params=params, headers=headers)

    if response.status_code >= 400:
        try:
            body = response.json()
            detail = body.get("detail") or body.get("message") or response.text
        except ValueError:
            detail = response.text
        raise ToolError(f"AmCAT API error {response.status_code}: {detail}")

    return response
