"""API Endpoints for API key management."""

from datetime import datetime, timezone
from typing import Annotated

from elastic_transport import ApiError
from fastapi import APIRouter, Body, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field

from amcat4.api.auth import authenticated_user
from amcat4.models import (
    ApiKeyRestrictions,
    User,
)
from amcat4.systemdata.apikeys import HTTPException_if_cannot_edit_api_keys, create_api_key, list_api_keys, update_api_key

app_api_keys = APIRouter(prefix="", tags=["api keys"])


class ApiKeyListResponse(BaseModel):
    """A list of API keys for the authenticated user."""

    id: str = Field(..., description="The ID of the API key.")
    name: str = Field(..., description="The name of the API key.")
    expires_at: str = Field(..., description="The expiration date of the API key.")
    restrictions: ApiKeyRestrictions = Field(..., description="The access restrictions of the API key.")


class ApiKeyUpdateResponse(BaseModel):
    """Response model for creating or updating an API key."""

    api_key: str | None = Field(
        None,
        description="The API key if it was created or regenerated (otherwise None). This is only shown once.",
    )


@app_api_keys.get("/api_keys")
async def get_api_keys(user: User = Depends(authenticated_user)):
    """Get statistics for a specific field. Only works for numeric (incl date) fields. Requires READER or METAREADER role."""

    api_keys = []
    async for id, api_key in list_api_keys(user):
        api_keys.append(
            ApiKeyListResponse(
                id=id,
                name=api_key.name,
                expires_at=api_key.expires_at.isoformat(),
                restrictions=api_key.restrictions,
            )
        )
    return api_keys


@app_api_keys.post("/api_keys")
async def post_api_key(
    name: Annotated[str, Body(description="The name of the API key.")],
    expires_at: Annotated[str, Body(description="The expiration date of the API key in ISO format.")],
    restrictions: Annotated[
        ApiKeyRestrictions | None,
        Body(description="The role restrictions for the API key."),
    ] = None,
    user: User = Depends(authenticated_user),
) -> ApiKeyUpdateResponse:
    """Create a new API key for the authenticated user."""
    HTTPException_if_cannot_edit_api_keys(user)

    id, api_key = await create_api_key(
        email=user.email or "",
        name=name,
        expires_at=iso_to_datetime(expires_at),
        role_restrictions=restrictions or ApiKeyRestrictions(),
    )

    return ApiKeyUpdateResponse(api_key=api_key)


@app_api_keys.delete("/api_keys/{api_key_id}")
async def delete_api_key(
    api_key_id: Annotated[str, Path(description="The ID of the API key to delete.")],
    user: User = Depends(authenticated_user),
):
    """Delete an API key by its ID."""
    HTTPException_if_cannot_edit_api_keys(user)

    await delete_api_key(api_key_id)


@app_api_keys.put("/api_keys/{api_key_id}")
async def put_api_key(
    api_key_id: Annotated[str, Path(description="The ID of the API key to update.")],
    name: Annotated[str | None, Body(description="The new name of the API key.")] = None,
    expires_at: Annotated[str | None, Body(description="The new expiration date of the API key in ISO format.")] = None,
    restrictions: Annotated[
        ApiKeyRestrictions | None,
        Body(description="The new role restrictions for the API key."),
    ] = None,
    regenerate_key: Annotated[
        bool,
        Body(description="Whether to regenerate the API key."),
    ] = False,
    user: User = Depends(authenticated_user),
) -> ApiKeyUpdateResponse:
    """Update an existing API key."""
    HTTPException_if_cannot_edit_api_keys(user)

    new_api_key = await update_api_key(
        api_key_id=api_key_id,
        name=name,
        expires_at=iso_to_datetime(expires_at) if expires_at else None,
        restrictions=restrictions,
        regenerate_key=regenerate_key,
    )

    return ApiKeyUpdateResponse(api_key=new_api_key)


def iso_to_datetime(iso_str: str) -> datetime:
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ISO date format: " + iso_str)
