"""
User/Account and authentication endpoints.

AmCAT4 can use either Basic or Token-based authentication.
A client can request a token with basic authentication and store that token for future requests.
"""

from typing import Annotated
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from pydantic.networks import EmailStr

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


class ServerUserResponse(BaseModel):
    email: RoleEmailPattern = Field(
        description="The closest email address the user matches to. Can be an exact email address (user@domain.com), domain wildcard (*@domain.com) or guest wildcard (*)",
    )
    role: Role = Field(description="The user role associate to this email address, domain or guest")


class CreateUserBody(BaseModel):
    """Form to create a new global user."""

    email: RoleEmailPattern
    role: ServerRole


class ChangeUserBody(BaseModel):
    """Form to change a global user."""

    role: ServerRole


# TODO: should we also rename users, since it's actually roles now?


@app_users.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(new_user: CreateUserBody, user=Depends(authenticated_user)):
    """Create a new user."""
    raise_if_not_server_role(user, Roles.ADMIN)
    create_server_role(new_user.email, role=Roles[new_user.role])


@app_users.get("/users/me")
def get_current_user(user: User = Depends(authenticated_user)) -> ServerUserResponse:
    """View the current user."""
    role = get_user_server_role(user)
    return ServerUserResponse(email=role.email, role=role.role)


@app_users.get("/users/{email}")
def get_user(email: RoleEmailPattern, current_user: User = Depends(authenticated_user)) -> ServerUserResponse:
    """
    View a specified current user.

    Only WRITER and ADMIN can view other users.
    """
    if current_user.email and current_user.email != email:
        raise_if_not_server_role(current_user, Roles.WRITER)
    role = get_user_server_role(User(email=email))
    return ServerUserResponse(email=role.email, role=role.role)


@app_users.get("/users")
def list_global_users(user=Depends(authenticated_user)):
    """List all global users"""
    raise_if_not_server_role(user, Roles.WRITER)
    server_roles = list_server_roles()
    return [{"email": role.email, "role": role.role} for role in server_roles]


@app_users.delete("/users/{email}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_user(email: RoleEmailPattern, current_user: User = Depends(authenticated_user)):
    """
    Delete the given user.
    Users can delete themselves and admin can delete everyone
    """
    if current_user.email != email:
        raise_if_not_server_role(current_user, Roles.ADMIN)

    delete_server_role(email=email)


@app_users.put("/users/{email}")
def modify_user(email: RoleEmailPattern, data: ChangeUserBody, user: User = Depends(authenticated_user)):
    """
    Modify the given user.
    Only admin can change users.
    """
    raise_if_not_server_role(user, Roles.ADMIN)
    update_server_role(email=email, role=Roles[data.role])
