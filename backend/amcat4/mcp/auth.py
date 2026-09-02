"""
Authentication middleware for the MCP endpoint.

Auth semantics deliberately mirror the REST API (see `authenticated_user` in
amcat4.api.auth_helpers): requests carry an AmCAT API key, either as
`X-API-Key: ak....` or `Authorization: Bearer ak....` (many MCP clients only
support bearer headers). The key is stashed in a ContextVar and forwarded as
X-API-Key when tools call the REST API in-process, so all existing role
checks and API-key restrictions apply unchanged.

Keyless requests mirror REST semantics too: under `no_auth` and
`allow_guests` they proceed as anonymous guests (index-level guest roles
apply); under `allow_authenticated_guests` they are rejected with a
transport-level 401, which MCP clients understand as "credentials required".

Future work: OAuth 2.1 with RFC 9728 protected-resource metadata (would
enable e.g. claude.ai web connectors).
"""

import json

from starlette.types import ASGIApp, Receive, Scope, Send

from amcat4.config import AuthOptions, get_settings
from amcat4.mcp.client import api_key_var

MISSING_KEY_DETAIL = (
    "This server requires authentication. Send an AmCAT API key as 'X-API-Key: ak....' or 'Authorization: Bearer ak....'"
)


def _extract_api_key(scope: Scope) -> str | None:
    api_key = None
    bearer = None
    for name, value in scope["headers"]:
        if name == b"x-api-key":
            api_key = value.decode("latin-1").strip()
        elif name == b"authorization":
            header = value.decode("latin-1")
            if header.lower().startswith("bearer "):
                bearer = header[len("bearer ") :].strip()
    return api_key or bearer


class MCPAuthMiddleware:
    """Pure-ASGI middleware (no response buffering) guarding /mcp requests."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        api_key = _extract_api_key(scope)

        if api_key is None and get_settings().auth == AuthOptions.allow_authenticated_guests:
            body = json.dumps({"detail": MISSING_KEY_DETAIL}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        (b"www-authenticate", b"Bearer"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        token = api_key_var.set(api_key)
        try:
            await self.app(scope, receive, send)
        finally:
            api_key_var.reset(token)
