import hashlib
import secrets
from datetime import UTC, datetime
from typing import AsyncIterable

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import EmailStr

from amcat4.errors import NotFoundError
from amcat4.models import ApiKey, ApiKeyRestrictions, User
from amcat4.postgres.connection import execute, fetch_all, fetch_one

_COLUMNS = "id, email, name, hashed_key, expires_at, jkt, restrictions"


async def get_api_key(api_key: str) -> ApiKey:
    row = await fetch_one(f"SELECT {_COLUMNS} FROM api_keys WHERE hashed_key = %s", [hash_api_key(api_key)])  # type: ignore[arg-type]
    if row is None:
        raise KeyError("API key not found")

    doc = _apikey_from_row(row)
    if doc.expires_at < datetime.now(tz=UTC):
        raise KeyError("API key has expired")

    return doc


async def list_api_keys(user: User) -> AsyncIterable[tuple[str, ApiKey]]:
    rows = await fetch_all(f"SELECT {_COLUMNS} FROM api_keys WHERE email = %s ORDER BY name", [user.email])  # type: ignore[arg-type]
    for row in rows:
        yield row["id"], _apikey_from_row(row)


async def create_api_key(
    email: EmailStr, name: str, expires_at: datetime, restrictions: ApiKeyRestrictions
) -> tuple[str, str]:
    api_key = await generate_api_key()
    row = await fetch_one(
        """INSERT INTO api_keys (email, name, hashed_key, expires_at, restrictions)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        [email, name, hash_api_key(api_key), expires_at, Jsonb(restrictions.model_dump(exclude_none=True))],
    )
    assert row is not None
    return row["id"], api_key


async def update_api_key(
    api_key_id: str,
    name: str | None = None,
    expires_at: datetime | None = None,
    restrictions: ApiKeyRestrictions | None = None,
    regenerate_key: bool = False,
) -> None | str:
    doc: dict = {}
    new_api_key = await generate_api_key() if regenerate_key else None

    if name is not None:
        doc["name"] = name
    if expires_at is not None:
        doc["expires_at"] = expires_at
    if restrictions is not None:
        doc["restrictions"] = Jsonb(restrictions.model_dump(exclude_none=True))
    if new_api_key is not None:
        doc["hashed_key"] = hash_api_key(new_api_key)

    if doc:
        # restrictions are merged with the existing restrictions (like the previous elastic implementation did)
        assignments = ", ".join(f"{k} = restrictions || %s" if k == "restrictions" else f"{k} = %s" for k in doc)
        n = await execute(f"UPDATE api_keys SET {assignments} WHERE id = %s", [*doc.values(), api_key_id])  # type: ignore[arg-type]
        if n == 0:
            raise NotFoundError(f"API key {api_key_id} does not exist")

    return new_api_key


async def delete_api_key(api_key_id: str) -> None:
    n = await execute("DELETE FROM api_keys WHERE id = %s", [api_key_id])
    if n == 0:
        raise NotFoundError(f"API key {api_key_id} does not exist")


async def generate_api_key() -> str:
    for attempt in range(5):
        bytes = secrets.token_urlsafe(32)
        prefix = "ak"  # prefix for identifying api keys
        api_key = f"{prefix}.{bytes}"
        if await fetch_one("SELECT 1 FROM api_keys WHERE hashed_key = %s", [hash_api_key(api_key)]):
            continue  # collision, try again
        return api_key

    raise RuntimeError("Failed to generate valid API key")


def hash_api_key(api_key: str) -> str:
    """Hash an API key using SHA-256."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def HTTPException_if_cannot_edit_api_keys(user: User) -> None:
    if not user.email:
        raise HTTPException(401, "User must be authenticated to create an API key")
    if user.api_key_restrictions and not user.api_key_restrictions.edit_api_keys:
        raise HTTPException(403, f"API key '{user.api_key_name}' is not allowed to edit API keys")


def _apikey_from_row(row: dict) -> ApiKey:
    return ApiKey.model_validate({k: v for k, v in row.items() if k != "id"})
