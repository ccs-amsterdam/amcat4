"""API Endpoints for managing global users and roles."""

from typing import Annotated
from click.core import F
from fastapi import APIRouter, Body, Depends, Response, status
from pydantic import BaseModel, Field

from amcat4.api.auth import authenticated_user
from amcat4.models import Role, Roles, RoleEmailPattern, ServerRole, User
from amcat4.systemdata.roles import (
    create_server_role,
    delete_server_role,
    get_user_server_role,
    list_server_roles,
    raise_if_not_server_role,
    update_server_role,
)

app_users = APIRouter(tags=["users"])


# REQUEST MODELS
class CreateUserBody(BaseModel):
    """Body for creating a new global user/role."""

    email: RoleEmailPattern = Field(
        ...,
        description="Email address of the user to add. Can also be a domain wildcard (*@example.com) or guest wildcard (*).",
    )
    role: ServerRole = Field(..., description="Server role to grant to the user.")


class UpdateUserBody(BaseModel):
    """Body for updating a global user/role."""

    role: ServerRole = Field(..., description="New role for the user.")
    upsert: bool = Field(
        False,
        description="If true, create the user role if it does not exist.",
    )


# RESPONSE MODELS
class ServerUserResponse(BaseModel):
    """Response for a global user/role."""

    email: RoleEmailPattern = Field(
        description="The email pattern for this role (e.g., user@example.com, *@example.com, or *).",
    )
    role: Role = Field(description="The role assigned to the user.")


@app_users.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(new_user: CreateUserBody, user=Depends(authenticated_user)) -> ServerUserResponse:
    """Create a new global user/role. Requires ADMIN server role."""
    raise_if_not_server_role(user, Roles.ADMIN)
    create_server_role(new_user.email, role=Roles[new_user.role])
    return ServerUserResponse(email=new_user.email, role=new_user.role)


@app_users.get("/users/me")
def get_current_user(user: User = Depends(authenticated_user)) -> ServerUserResponse:
    """Get the current user's global role."""
    role = get_user_server_role(user)
    return ServerUserResponse(email=role.email, role=role.role)


@app_users.get("/users/{email}")
def get_user(email: RoleEmailPattern, current_user: User = Depends(authenticated_user)) -> ServerUserResponse:
    """
    Get a specified user's global role. Requires WRITER server role if viewing other users.
    """
    if current_user.email and current_user.email != email:
        raise_if_not_server_role(current_user, Roles.WRITER)
    role = get_user_server_role(User(email=email))
    return ServerUserResponse(email=role.email, role=role.role)


@app_users.get("/users")
def list_global_users(user=Depends(authenticated_user)) -> list[ServerUserResponse]:
    """List all global users/roles. Requires WRITER server role."""
    raise_if_not_server_role(user, Roles.WRITER)
    server_roles = list_server_roles()
    return [ServerUserResponse(email=role.email, role=role.role) for role in server_roles]


@app_users.delete("/users/{email}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(email: RoleEmailPattern, current_user: User = Depends(authenticated_user)):
    """
    Delete a global user/role. Users can delete themselves, and ADMINs can delete any user/role.
    """
    if current_user.email != email:
        raise_if_not_server_role(current_user, Roles.ADMIN)

    delete_server_role(email=email)


@app_users.put("/users/{email}")
def modify_user(
    email: RoleEmailPattern, body: Annotated[UpdateUserBody, Body(...)], user: User = Depends(authenticated_user)
) -> ServerUserResponse:
    """
    Modify a global user/role. Requires ADMIN server role.
    """
    raise_if_not_server_role(user, Roles.ADMIN)
    update_server_role(email=email, role=Roles[body.role], ignore_missing=body.upsert)
    return ServerUserResponse(email=email, role=body.role)
