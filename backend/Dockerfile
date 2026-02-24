FROM python:3.11-alpine3.19 AS builder

# 1 Install system dependencies and uv
RUN apk add --update --no-cache git gcc libc-dev libffi-dev libmagic
# Get uv from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /srv/amcat

# 2 Clone the repo
COPY . .

# 3 Install amcat using uv
RUN UV_LINK_MODE=copy uv sync --frozen --no-dev

# Start a new image without build dependencies and copy the build
FROM python:3.11-alpine3.19
WORKDIR /srv/amcat

RUN apk add --update --no-cache libmagic

COPY --from=builder /srv/amcat/.venv /srv/amcat/.venv
COPY --from=builder /srv/amcat /srv/amcat

ENV PATH="/srv/amcat/.venv/bin:$PATH"
EXPOSE 5000
CMD ["amcat4", "run"]
