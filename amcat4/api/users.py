"""
AmCAT4 can use either Basic or Token-based authentication.
A client can request a token with basic authentication and store that token for future requests.
"""
import logging
from typing import Literal, Optional, Union

from fastapi import APIRouter, HTTPException, status, Response
from fastapi.params import Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from pydantic.networks import EmailStr

from amcat4 import auth
from amcat4.api.auth import authenticated_user, authenticated_writer, check_role
from amcat4.api.common import _index
from amcat4.auth import Role, User, hash_password

app_users = APIRouter(

    tags=["users"])


class Username(EmailStr):
    """Subclass of EmailStr to allow 'admin' username. """
    # WVA: Not sure we should actually keep admin?
    @classmethod
    def validate(cls, value: Union[str]) -> str:
        if value == "admin":
            return "admin"
        return super().validate(value)


ROLE = Literal["ADMIN", "WRITER", "admin", "writer"]


class UserForm(BaseModel):
    email: Username
    password: str
    global_role: Optional[ROLE]
    index_access: Optional[str]


class ChangeUserForm(BaseModel):
    email: Optional[Username]
    password: Optional[str]
    global_role: Optional[ROLE]


@app_users.post("/users/", status_code=status.HTTP_201_CREATED)
def create_user(new_user: UserForm, current_user: User = Depends(authenticated_writer)):
    """
    Create a new user. Request body should be a json with email, password, and optional (global) role
    """
    if User.select().where(User.email == new_user.email).exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"User {new_user.email} already exists")
    role = Role[new_user.global_role.upper()] if new_user.global_role else None
    if role == Role.ADMIN:
        check_role(current_user, Role.ADMIN)
    u = auth.create_user(email=new_user.email, password=new_user.password, global_role=role)
    if new_user.index_access:
        _index(new_user.index_access).set_role(u, role or Role.READER)
    return {"id": u.id, "email": u.email}


@app_users.get("/users/me")
def get_current_user(current_user: User = Depends(authenticated_user)):
    """
    View the current user.
    """
    return {"email": current_user.email, "global_role": current_user.role and current_user.role.name}


@app_users.get("/users/{email}")
def get_user(email: Username, current_user: User = Depends(authenticated_user)):
    """
    View the current user. Users can view themselves, writer can view others
    """
    if current_user.email != email:
        check_role(current_user, Role.WRITER)
    try:
        u = User.get(User.email == email)
        return {"email": u.email, "global_role": u.role and u.role.name}
    except User.DoesNotExist:
        raise HTTPException(404, detail=f"User {email} unknown")


@app_users.get("/users", dependencies=[Depends(authenticated_writer)])
def list_users():
    result = []
    res1 = [dict(user=u.email, role=u.global_role) for u in User.select()]
    for entry in res1:
        for ix, role in User.get(User.email == entry['user']).indices().items():
            result.append(dict(user=entry['user'], index_name=ix.name, role=role.name))
    return result


@app_users.delete("/users/{email}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_user(email: Username, current_user: User = Depends(authenticated_user)):
    """
    Delete the given user. Users can delete themselves, admin can delete everyone, and writer can delete non-admin
    """
    if current_user.email != email:
        check_role(current_user, Role.WRITER)
    try:
        u = User.get(User.email == email)
    except User.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"User {email} does not exist")
    if u.role == Role.ADMIN:
        check_role(current_user, Role.ADMIN)
    u.delete_instance()


@app_users.put("/users/{email}")
def modify_user(email: Username, data: ChangeUserForm, current_user: User = Depends(authenticated_user)):
    """
    Modify the given user.
    Users can modify themselves (but not their role), admin can change everyone, and writer can change non-admin.
    """
    if current_user.email != email:
        check_role(current_user, Role.WRITER)
    try:
        u = User.get(User.email == email)
    except User.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"User {email} does not exist")
    if u.role == Role.ADMIN:
        check_role(current_user, Role.ADMIN)
    if data.global_role:
        role = Role[data.global_role.upper()]
        check_role(current_user, role)  # need at least same level
        logging.info(f"Changing {email} to {role}")
        u.global_role = role
    if data.email:
        u.email = data.email
    if data.password:
        u.password = hash_password(data.password)
    u.save()
    return {"email": u.email, "global_role": u.role and u.role.name}


@app_users.post("/auth/token")
def get_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Create a new token for the authenticated user
    """
    user = auth.verify_user(email=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    token = user.create_token()
    return {"access_token": token, "token_type": "bearer"}


@app_users.get("/auth/token")
def refresh_token(current_user: User = Depends(authenticated_user)):
    """
    Create a new token for the authenticated user
    """
    token = current_user.create_token()
    return {"access_token": token, "token_type": "bearer"}
