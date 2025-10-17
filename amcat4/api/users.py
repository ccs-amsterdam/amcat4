"""
User/Account and authentication endpoints.

AmCAT4 can use either Basic or Token-based authentication.
A client can request a token with basic authentication and store that token for future requests.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from pydantic.networks import EmailStr

from amcat4.api.auth import authenticated_user
from amcat4.models import Role, RoleEmailPattern, User
from amcat4.systemdata.roles import (
    create_role,
    list_roles,
    get_user_server_role,
    raise_if_not_project_index_role,
    raise_if_not_server_role,
    update_role,
)

app_users = APIRouter(tags=["users"])


class UserForm(BaseModel):
    """Form to create a new global user."""

    email: RoleEmailPattern
    role: Role


class ChangeUserForm(BaseModel):
    """Form to change a global user."""

    role: Role


# TODO: should we also rename users, since it's actually roles now?


@app_users.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(new_user: UserForm, user=Depends(authenticated_user)):
    """Create a new user."""
    raise_if_not_project_index_role(user, "_server", Role.ADMIN)
    create_role(new_user.email, role_context="_server", role=new_user.role)
    return {"email": new_user.email, "global_role": new_user.role}


@app_users.get("/users/me")
def get_current_user(user: User = Depends(authenticated_user)):
    """View the current user."""
    return _get_user(user.email)


@app_users.get("/users/{email}")
def get_user(email: EmailStr, current_user: User = Depends(authenticated_user)):
    """
    View a specified current user.

    Only WRITER and ADMIN can view other users.
    """
    raise_if_not_project_index_role(current_user, "_server", Role.WRITER)
    return _get_user(email)


def _get_user(email: EmailStr | None):
    role = get_user_server_role(User(email=email))
    if role:
        return {"email": email, "role": role, "role_match": role.email_pattern}
    else:
        return {"email": email, "role": None, "role_match": None}


@app_users.get("/users")
def list_global_users(user=Depends(authenticated_user)):
    """List all global users"""
    raise_if_not_project_index_role(user, "_server", Role.WRITER)
    server_roles = list_roles(role_contexts=["_server"])
    return [{"email": role.email_pattern, "role": role.role.name} for role in server_roles]


@app_users.delete("/users/{email}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_user(email: EmailStr, current_user: User = Depends(authenticated_user)):
    """
    Delete the given user.
    Users can delete themselves and admin can delete everyone
    """
    if current_user != email:
        raise_if_not_server_role(current_user, Role.ADMIN)

    update_role(email_pattern=email, role_context="_server", role=Role.NONE)


@app_users.put("/users/{email}")
def modify_user(email: EmailStr, data: ChangeUserForm, user: User = Depends(authenticated_user)):
    """
    Modify the given user.
    Only admin can change users.
    """
    update_role(email_pattern=email, role_context="_server", role=data.role)
    return {"email": email, "role": data.role.name}
