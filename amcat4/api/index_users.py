"""API Endpoints for project user management."""

from typing import Annotated

from elasticsearch import ConflictError, NotFoundError
from fastapi import APIRouter, Body, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field

from amcat4.api.auth import authenticated_user
from amcat4.models import (
    IndexId,
    Role,
    RoleEmailPattern,
    Roles,
    User,
)
from amcat4.systemdata.roles import (
    HTTPException_if_not_project_index_role,
    create_project_role,
    delete_project_role,
    list_project_roles,
    update_project_role,
)

app_index_users = APIRouter(prefix="", tags=["project users"])


# REQUEST MODELS
class CreateIndexUserBody(BaseModel):
    """Body for adding a user to an index."""

    email: RoleEmailPattern = Field(..., description="Email address of the user to add.")
    role: Role = Field(..., description="Role to grant to the user.")


class UpdateIndexUserBody(BaseModel):
    """Body for updating a user's role in an index."""

    role: Role = Field(..., description="New role for the user.")
    upsert: bool = Field(
        False,
        description="If true, create the user role if it does not exist.",
    )


# RESPONSE MODELS
class IndexUserResponse(BaseModel):
    """Response for an index user."""

    email: RoleEmailPattern = Field(
        ...,
        description="The email pattern for this role (e.g., user@example.com, *@example.com, or *).",
    )
    role: Role = Field(..., description="The role assigned to the user.")


@app_index_users.get("/index/{ix}/users")
async def project_users(
    ix: Annotated[IndexId, Path(..., description="ID of the index to list users for")],
    user: User = Depends(authenticated_user),
) -> list[IndexUserResponse]:
    """
    List the users and their roles for a given index. Requires WRITER role on the index.
    """
    await HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
    roles = list_project_roles(project_ids=[ix])
    return [IndexUserResponse(email=r.email, role=r.role) async for r in roles]


@app_index_users.post("/index/{ix}/users", status_code=status.HTTP_201_CREATED)
async def add_project_user(
    ix: Annotated[IndexId, Path(..., description="ID of the index to list users for")],
    body: Annotated[CreateIndexUserBody, Body(...)],
    user: User = Depends(authenticated_user),
) -> IndexUserResponse:
    """
    Add a user to an index or update their role. Requires ADMIN role on the index.
    """
    await HTTPException_if_not_project_index_role(user, ix, Roles.ADMIN)
    try:
        await create_project_role(body.email, ix, Roles[body.role])
    except ConflictError:
        raise HTTPException(409, detail=f"User {body.email} already has a role on index {ix}")
    return IndexUserResponse(email=body.email, role=body.role)


@app_index_users.put("/index/{ix}/users/{email}", status_code=status.HTTP_200_OK)
async def modify_project_user(
    ix: Annotated[IndexId, Path(description="ID of the index to list users for")],
    email: Annotated[RoleEmailPattern, Path(..., description="Email address of the user to modify")],
    body: Annotated[UpdateIndexUserBody, Body(...)],
    user: User = Depends(authenticated_user),
) -> IndexUserResponse:
    """
    Change the role of a user in an index. Requires ADMIN role on the index.
    """
    await HTTPException_if_not_project_index_role(user, ix, Roles.ADMIN)
    try:
        await update_project_role(email, ix, Roles[body.role], ignore_missing=body.upsert)
    except NotFoundError:
        raise HTTPException(
            404,
            detail=f"Cannot modify User {email}, because this user does not have a role on index {ix} yet. Create new user or use upsert",
        )
    return IndexUserResponse(email=email, role=body.role)


@app_index_users.delete("/index/{ix}/users/{email}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project_user(
    ix: Annotated[IndexId, Path(..., description="ID of the index to list users for")],
    email: Annotated[RoleEmailPattern, Path(..., description="Email address of the user to modify")],
    user: User = Depends(authenticated_user),
):
    """
    Remove a user from an index. Requires ADMIN role on the index, unless a user is removing themselves.
    """
    if user.email != email:
        await HTTPException_if_not_project_index_role(user, ix, Roles.ADMIN)
    try:
        await delete_project_role(email, ix)
    except NotFoundError:
        raise HTTPException(404, detail=f"User {email} does not have a role on index {ix}")
