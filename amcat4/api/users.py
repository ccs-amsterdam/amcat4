"""
User/Account and authentication endpoints.

AmCAT4 can use either Basic or Token-based authentication.
A client can request a token with basic authentication and store that token for future requests.
"""
from typing import Literal, Optional, Union

from fastapi import APIRouter, HTTPException, status, Response
from fastapi.params import Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from pydantic.networks import EmailStr

from amcat4 import index
from amcat4.api import auth
from amcat4.api.auth import authenticated_user, create_token, authenticated_admin, check_global_role
from amcat4.config import get_settings
from amcat4.index import Role, set_global_role, get_global_role

app_users = APIRouter(

    tags=["users"])


class Username(EmailStr):
    """Subclass of EmailStr to allow 'admin' username."""

    # WVA: Not sure we should actually keep admin?
    @classmethod
    def validate(cls, value: Union[str]) -> str:
        """Check for valid email or 'admin'."""
        if value == "admin":
            return "admin"
        return super().validate(value)


ROLE = Literal["ADMIN", "WRITER", "admin", "writer"]


class UserForm(BaseModel):
    """Form to create a new global user."""
    email: Username
    global_role: Optional[ROLE]


class ChangeUserForm(BaseModel):
    """Form to change a global user."""
    global_role: Optional[ROLE]


@app_users.post("/users/", status_code=status.HTTP_201_CREATED)
def create_user(new_user: UserForm, current_user=Depends(authenticated_admin)):
    """Create a new user."""
    if get_global_role(new_user.email) is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"User {new_user.email} already exists")
    role = Role[new_user.global_role.upper()] if new_user.global_role else None
    set_global_role(email=new_user.email, role=role)
    return {"email": new_user.email, "global_role": role.value}


@app_users.get("/users/me")
def get_current_user(current_user: str = Depends(authenticated_user)):
    """View the current user."""
    return _get_user(current_user, current_user)


@app_users.get("/users/{email}")
def get_user(email: Username, current_user: str = Depends(authenticated_user)):
    """
    View a specified current user.

    Users can view themselves, writer can view others
    """
    return _get_user(email, current_user)


def _get_user(email, current_user):
    if current_user != email:
        check_global_role(current_user, Role.WRITER)
    global_role = get_global_role(email)
    if global_role is not None:
        return {"email": email, "global_role": global_role.name}
    else:
        raise HTTPException(404, detail=f"User {email} unknown")


@app_users.get("/users", dependencies=[Depends(authenticated_admin)])
def list_global_users():
    """List all global users"""
    return [{'email': email, 'global_role': role.name} for (email, role) in index.list_global_users()]


@app_users.delete("/users/{email}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_user(email: Username, current_user: str = Depends(authenticated_user)):
    """
    Delete the given user.

    Users can delete themselves and admin can delete everyone
    """
    if current_user != email:
        check_global_role(current_user, Role.ADMIN)
    index.delete_user(email)


@app_users.put("/users/{email}")
def modify_user(email: Username, data: ChangeUserForm, _user=Depends(authenticated_admin)):
    """
    Modify the given user.
    Only admin can change users.
    """
    role = Role[data.global_role.upper()]
    set_global_role(email, role)
    return {"email": email, "global_role": role.name}


@app_users.post("/auth/token")
def get_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Create a new token for the user authenticating with a form."""
    if form_data.username == "admin" and auth.verify_admin(password=form_data.password):
        token = create_token("admin")
        return {"access_token": token, "token_type": "bearer"}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")


@app_users.get("/auth/token")
def refresh_token(current_user: str = Depends(authenticated_user)):
    """Create a new token for the user authenticated with an existing token."""
    token = create_token(current_user)
    return {"access_token": token, "token_type": "bearer"}


@app_users.get("/middlecat")
def get_auth_config():
    return {"middlecat_url": get_settings().middlecat_url,
            "resource": get_settings().host,
            "allow_password": bool(get_settings().admin_password)}
