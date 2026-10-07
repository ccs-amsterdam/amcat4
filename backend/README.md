# AmCAT4 Backend

FastAPI-based REST API for the AmCAT text analysis platform.

## Tech Stack

- **Python 3.11+** with [uv](https://docs.astral.sh/uv/) for dependency management
- **FastAPI** + **Uvicorn** — async web framework and ASGI server
- **PostgreSQL** with **pg_search** (BM25 full-text search) and **pgvector** — data store for documents and system data (e.g. the `paradedb/paradedb` docker image)
- **psycopg 3** — async postgres driver
- **Pydantic / pydantic-settings** — data validation and configuration
- **Authlib** — OAuth/OIDC integration (via [MiddleCat](https://github.com/ccs-amsterdam/middlecat))
- **aioboto3** — async S3/SeaweedFS client for multimedia storage (optional)

## Project Structure

```
amcat4/
├── api/           # FastAPI route handlers (one file per resource)
├── projects/      # Business logic (no HTTP concerns)
├── postgres/      # Database layer: schema, query parser, search, documents, aggregation
├── auth/          # Auth helpers and CSRF
├── objectstorage/ # S3/SeaweedFS integration and image processing
├── systemdata/    # Users, roles, settings, fields, api keys, requests
├── config.py      # Settings (env vars prefixed AMCAT4_*)
├── connections.py # Database + S3 connection management
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

Requires PostgreSQL with pg_search running locally — start one via `pnpm start:db` (see the root README), or e.g.:

```bash
docker run -d -p 5432:5432 -e POSTGRES_USER=amcat -e POSTGRES_PASSWORD=amcat -e POSTGRES_DB=amcat paradedb/paradedb
```

## Testing

Tests use **pytest** with **pytest-anyio** (async) and **pytest-httpx** (mock HTTP). They run against a live postgres database (configured with `AMCAT4_POSTGRES_URL`), using a separate schema (`amcat_test`) that is created and dropped automatically. The multimedia tests are skipped unless S3 is configured (`AMCAT4_S3_HOST` etc.).

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
