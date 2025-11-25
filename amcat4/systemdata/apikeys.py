import hashlib
import secrets
from datetime import UTC, datetime
from typing import AsyncIterable

from fastapi import HTTPException
from pydantic import EmailStr

from amcat4.connections import es
from amcat4.elastic.util import index_scan
from amcat4.models import ApiKey, ApiKeyRestrictions, User
from amcat4.systemdata.versions.v2 import apikeys_index_name


async def get_api_key(api_key: str) -> ApiKey:
    hashed_key = hash_api_key(api_key)

    q = {"term": {"hashed_key": hashed_key}}
    res = await es().search(index=apikeys_index_name(), query=q, size=1)

    if res["hits"]["total"]["value"] == 0:
        raise KeyError("API key not found")

    doc = _apikey_from_elastic(res["hits"]["hits"][0]["_source"])
    if doc.expires_at < datetime.now(tz=UTC):
        raise KeyError("API key has expired")

    return doc


async def list_api_keys(user: User) -> AsyncIterable[tuple[str, ApiKey]]:
    q = {"term": {"email": user.email}}
    async for id, doc in index_scan(index=apikeys_index_name(), query=q):
        yield id, _apikey_from_elastic(doc)


async def create_api_key(
    email: EmailStr, name: str, expires_at: datetime, restrictions: ApiKeyRestrictions
) -> tuple[str, str]:
    api_key = await generate_api_key()

    doc = ApiKey(
        email=email,
        name=name,
        hashed_key=hash_api_key(api_key),
        expires_at=expires_at,
        restrictions=restrictions,
        jkt=None,
    )

    doc = await es().index(index=apikeys_index_name(), id=None, document=_apikey_to_elastic(doc), refresh=True)

    return doc["_id"], api_key


async def update_api_key(
    api_key_id: str,
    name: str | None = None,
    expires_at: datetime | None = None,
    restrictions: ApiKeyRestrictions | None = None,
    regenerate_key: bool = False,
) -> None | str:
    doc: dict = {}

    if regenerate_key:
        new_api_key = await generate_api_key()
    else:
        new_api_key = None

    if name is not None:
        doc["name"] = name
    if expires_at is not None:
        doc["expires_at"] = expires_at
    if restrictions is not None:
        doc["restrictions"] = restrictions.model_dump(exclude_none=True)
    if new_api_key is not None:
        doc["hashed_key"] = hash_api_key(new_api_key)

    if doc:
        await es().update(index=apikeys_index_name(), id=api_key_id, doc=doc, refresh=True)

    return new_api_key


async def delete_api_key(api_key_id: str) -> None:
    await es().delete(index=apikeys_index_name(), id=api_key_id)


async def generate_api_key() -> str:
    for attempt in range(5):
        bytes = secrets.token_urlsafe(32)
        prefix = "ak"  # prefix for identifying api keys
        api_key = f"{prefix}.{bytes}"

        q = {"term": {"hashed_key": hash_api_key(api_key)}}
        res = await es().search(index=apikeys_index_name(), query=q, size=0)
        if res["hits"]["total"]["value"] > 0:
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


def _apikey_from_elastic(d: dict) -> ApiKey:
    if "restrictions" in d:
        pr = d["restrictions"].get("project_roles")
        if pr is not None:
            d["restrictions"]["project_roles"] = {item["project_id"]: item["role"] for item in pr}
    return ApiKey.model_validate(d)


def _apikey_to_elastic(api_key: ApiKey) -> dict:
    d = api_key.model_dump()
    if "restrictions" in d:
        pr = d["restrictions"].get("project_roles")
        if pr is not None:
            d["restrictions"]["project_roles"] = [dict(project_id=k, role=v) for k, v in pr.items()]
    return d
