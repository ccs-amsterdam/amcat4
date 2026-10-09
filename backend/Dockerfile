FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /srv/amcat

# Install the dependencies first (cached as long as the lock file doesn't change), then the project itself
COPY pyproject.toml uv.lock ./
RUN UV_LINK_MODE=copy uv sync --frozen --no-dev --no-install-project
COPY . .
RUN UV_LINK_MODE=copy uv sync --frozen --no-dev

# Runtime image without uv and the build cache
FROM python:3.13-slim
WORKDIR /srv/amcat

RUN apt-get update && apt-get install -y --no-install-recommends libmagic1 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /srv/amcat /srv/amcat

ENV PATH="/srv/amcat/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 5000
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/config', timeout=4)"
CMD ["amcat4", "serve"]
