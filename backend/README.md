# AmCAT4 Backend

FastAPI-based REST API for the AmCAT text analysis platform.

## Tech Stack

- **Python 3.11+** with [uv](https://docs.astral.sh/uv/) for dependency management
- **FastAPI** + **Uvicorn** — async web framework and ASGI server
- **Elasticsearch 8.6+** — primary data store for documents and indexes
- **Pydantic / pydantic-settings** — data validation and configuration
- **Authlib** — OAuth/OIDC integration (via [MiddleCat](https://github.com/ccs-amsterdam/middlecat))
- **aioboto3** — async S3/SeaweedFS client for multimedia storage (optional)

## Project Structure

```
amcat4/
├── api/           # FastAPI route handlers (one file per resource)
├── projects/      # Business logic (no HTTP concerns)
├── elastic/       # Elasticsearch utilities
├── auth/          # Auth helpers and CSRF
├── objectstorage/ # S3/SeaweedFS integration and image processing
├── systemdata/    # System index management, migrations, roles
├── mcp/           # MCP (Model Context Protocol) server, mounted at /mcp
├── config.py      # Settings (env vars prefixed AMCAT4_*)
├── connections.py # Elasticsearch + S3 connection management
├── models.py      # Shared Pydantic models
└── __main__.py    # CLI entry point
```

## Configuration

Configuration is read from environment variables and/or a `.env` file in the working directory (or at the path set by `AMCAT4_CONFIG_FILE`). See [`deploy/.env.example`](../deploy/.env.example) for available settings.

To generate a starter `.env` file interactively:

```bash
uv run amcat4 config
```

## Running & CLI

```bash
uv sync                   # Install dependencies
uv run amcat4 run         # Start the development server (port 5000, auto-reload)
uv run amcat4 --help      # List all available CLI commands
```

The API will be available at `http://localhost:5000`. Interactive docs at `/docs`.

Requires Elasticsearch 8.17+ running locally — start one via the root `docker-compose.yml`.

## MCP server

AmCAT4 also serves an [MCP](https://modelcontextprotocol.io) (Model Context Protocol) endpoint at `/mcp`, on the same host and port as the REST API (e.g. `http://localhost:5000/mcp` locally, `https://<host>/mcp` in production). This lets LLM clients (Claude Code, Claude Desktop, Cursor, …) query indices, retrieve documents, and write annotations back — e.g. create a `sentiment` field and then set its value per document.

**Auth**: MCP requests authenticate with a regular AmCAT API key (mint one in the UI or via `POST /api/api_keys`), sent as either `X-API-Key: ak....` or `Authorization: Bearer ak....` (many MCP clients only support bearer headers). All existing roles and API-key restrictions apply exactly as they do for the REST API — the MCP server forwards every tool call to the REST endpoints in-process. On servers with `auth = allow_guests`, requests without a key are treated as anonymous guests (index-level guest roles apply); on `allow_authenticated_guests`, a missing key gets a `401` before any tool runs.

**Tools**: `list_indices`, `get_index`, `list_fields`, `get_field_values`, `get_field_stats`, `query_documents`, `aggregate_documents`, `get_document`, `update_document`, `create_field`, `update_documents_by_query`, `update_tags`. Typical annotation workflow: `list_indices` → `list_fields` → `query_documents` → `create_field` (once, e.g. type `keyword` or `tag`) → `update_document` per document.

Set `amcat4_mcp_enabled=false` to disable the endpoint entirely (restart required). Implementation lives in `amcat4/mcp/`. Full OAuth 2.1 (needed for claude.ai web connectors) is future work — v1 is API-key pass-through only.

### Connect with Claude Code

1. Mint an API key: in the AmCAT web UI, or `POST /api/api_keys` with a session cookie.
2. Register the server:

   ```bash
   # Production / any deployed server
   claude mcp add --transport http amcat https://<host>/mcp --header "X-API-Key: ak...."

   # Local dev (uv run amcat4 run, default no_auth — no key needed)
   claude mcp add --transport http amcat-local http://localhost:5000/mcp
   ```

   Add `--scope project` to check the connection into `.mcp.json` for the team, or `--scope user` to keep it personal (default `local` only applies to the current project for you). Auth on servers with `no_auth` or `allow_guests` works without `--header` (guest permissions apply).
3. Start (or restart) Claude Code in the project, then run `/mcp` to confirm `amcat` shows as connected and lists the tools above.
4. `claude mcp list` shows configured servers; `claude mcp remove amcat` removes one.

Once connected, just ask Claude Code to query or annotate an AmCAT index by name — e.g. "list the fields on index X" or "tag all documents matching 'climate' with sentiment=negative".

## Testing

Tests use **pytest** with **pytest-anyio** (async) and **pytest-httpx** (mock HTTP). They run against a live Elasticsearch instance, creating and tearing down prefixed (`amcat4_unittest_*`) indexes automatically.

```bash
uv run pytest
```

Fixtures and shared utilities are in `tests/conftest.py`.

## Linting & Type Checking

```bash
uv run ruff check .      # Lint
uv run ruff format .     # Format
uv run basedpyright      # Type check
```

Configuration is in `pyproject.toml`. Install pre-commit hooks with `uv run pre-commit install`.
