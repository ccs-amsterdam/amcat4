"""
User/Account and authentication endpoints.

AmCAT4 can use either Basic or Token-based authentication.
A client can request a token with basic authentication and store that token for future requests.
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from pydantic.networks import EmailStr

from amcat4 import index
from amcat4.api.auth import authenticated_user
from amcat4.index import Role, set_global_role, user_exists
from amcat4.models import User
from amcat4.systemdata.roles import get_server_role, raise_if_not_project_index_role, raise_if_not_server_role

app_users = APIRouter(tags=["users"])


ROLE = Literal["ADMIN", "WRITER", "READER", "NONE"]


class UserForm(BaseModel):
    """Form to create a new global user."""

    email: EmailStr
    role: Optional[ROLE] = None


class ChangeUserForm(BaseModel):
    """Form to change a global user."""

    role: Optional[ROLE] = None


@app_users.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(new_user: UserForm, user=Depends(authenticated_user)):
    """Create a new user."""
    raise_if_not_project_index_role(user, "_server", "ADMIN")
    if user_exists(new_user.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User {new_user.email} already exists",
        )
    if new_user.role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User requires a role (one of {', '.join([r.name for r in Role])})",
        )
    role = Role[new_user.role.upper()]
    set_global_role(email=new_user.email, role=role)
    return {"email": new_user.email, "global_role": role.value}


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
    raise_if_not_project_index_role(current_user, "_server", "WRITER")
    return _get_user(email)


def _get_user(email: EmailStr | None):
    role = get_server_role(email)
    if role:
        return {"email": email, "role": role, "role_match": role.role_match}
    else:
        return {"email": email, "role": None, "role_match": None}


@app_users.get("/users")
def list_global_users(user=Depends(authenticated_user)):
    """List all global users"""
    raise_if_not_project_index_role(user, "_server", "WRITER")
    return [{"email": email, "role": role.name} for (email, role) in index.list_global_users().items()]


@app_users.delete("/users/{email}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_user(email: EmailStr, current_user: User = Depends(authenticated_user)):
    """
    Delete the given user.

    Users can delete themselves and admin can delete everyone
    """
    if current_user != email:
        raise_if_not_server_role(current_user, "ADMIN")
    index.delete_user(email)


@app_users.put("/users/{email}")
def modify_user(email: EmailStr, data: ChangeUserForm, user: User = Depends(authenticated_user)):
    """
    Modify the given user.
    Only admin can change users.
    """
    if data.role is None or data.role == "NONE":
        set_global_role(email, None)
        return {"email": email, "role": None}
    else:
        role = Role[data.role.upper()]
        set_global_role(email, role)
        return {"email": email, "role": role.name}
