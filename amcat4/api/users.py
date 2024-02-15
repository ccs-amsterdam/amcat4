"""
User/Account and authentication endpoints.

AmCAT4 can use either Basic or Token-based authentication.
A client can request a token with basic authentication and store that token for future requests.
"""

from typing import Literal, Optional
from importlib.metadata import version

from fastapi import APIRouter, HTTPException, status, Response, Depends
from pydantic import BaseModel
from pydantic.networks import EmailStr

from amcat4 import index
from amcat4.api.auth import authenticated_user, authenticated_admin, check_global_role
from amcat4.config import get_settings, validate_settings
from amcat4.index import Role, set_global_role, get_global_role, user_exists

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
def create_user(new_user: UserForm, _=Depends(authenticated_admin)):
    """Create a new user."""
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
def get_current_user(current_user: str = Depends(authenticated_user)):
    """View the current user."""
    return _get_user(current_user, current_user)


@app_users.get("/users/{email}")
def get_user(email: EmailStr, current_user: str = Depends(authenticated_user)):
    """
    View a specified current user.

    Users can view themselves, writer can view others
    """
    return _get_user(email, current_user)


def _get_user(email, current_user):
    if current_user != email:
        check_global_role(current_user, Role.WRITER)
    global_role = get_global_role(email)
    if email in ("admin", "guest") or global_role is None:
        raise HTTPException(404, detail=f"User {email} unknown")
    else:
        return {"email": email, "role": global_role.name}


@app_users.get("/users", dependencies=[Depends(authenticated_admin)])
def list_global_users():
    """List all global users"""
    return [{"email": email, "role": role.name} for (email, role) in index.list_global_users().items()]


@app_users.delete("/users/{email}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_user(email: EmailStr, current_user: str = Depends(authenticated_user)):
    """
    Delete the given user.

    Users can delete themselves and admin can delete everyone
    """
    if current_user != email:
        check_global_role(current_user, Role.ADMIN)
    index.delete_user(email)


@app_users.put("/users/{email}")
def modify_user(email: EmailStr, data: ChangeUserForm, _user: str = Depends(authenticated_admin)):
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


@app_users.get("/config")
@app_users.get("/middlecat")
def get_auth_config():
    return {
        "middlecat_url": get_settings().middlecat_url,
        "resource": get_settings().host,
        "authorization": get_settings().auth,
        "warnings": [validate_settings()],
        "api_version": version("amcat4"),
    }
