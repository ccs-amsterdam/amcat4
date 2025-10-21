"""API Endpoints for document and index management."""

from fastapi import APIRouter, Body, Depends, status
from pydantic import BaseModel

from amcat4.api.auth import authenticated_user
from amcat4.models import (
    IndexId,
    Roles,
    Role,
    User,
)
from amcat4.systemdata.roles import (
    create_project_role,
    delete_project_role,
    list_project_roles,
    raise_if_not_project_index_role,
    update_project_role,
)

app_index_users = APIRouter(prefix="", tags=["project users"])


class IndexUserResponse(BaseModel):
    email: str
    role: Role


@app_index_users.get("/index/{ix}/users")
def list_index_users(ix: IndexId, user: User = Depends(authenticated_user)) -> list[IndexUserResponse]:
    """
    List the users in this index.

    Allowed for global admin and local writers

    """
    # TODO: This used to be accessible to readers as well, but that doesn't seem
    #       right. Maybe we should even restrict to ADMINs, or at least require an exact email match?
    raise_if_not_project_index_role(user, ix, Roles.WRITER)
    roles = list_project_roles(project_ids=[ix])
    return [IndexUserResponse(email=r.email, role=r.role) for r in roles]


@app_index_users.post("/index/{ix}/users", status_code=status.HTTP_201_CREATED)
def add_index_users(
    ix: IndexId,
    email: str = Body(..., description="Email address of the user to add"),
    role: Role = Body(..., description="Role of the user to add"),
    user: User = Depends(authenticated_user),
):
    """
    Add an existing user to this index.

    This requires ADMIN rights on the index or server
    """
    raise_if_not_project_index_role(user, ix, Roles.ADMIN)
    create_project_role(email, ix, Roles[role])


@app_index_users.put("/index/{ix}/users/{email}", status_code=status.HTTP_200_OK)
def modify_index_user(
    ix: IndexId,
    email: str,
    role: Role = Body(..., description="New role for the user", embed=True),
    user: User = Depends(authenticated_user),
):
    """
    Change the role of an existing user.

    This requires ADMIN rights on the index or server
    """
    # TODO: this is now identical to add_index_user. Should we merge,
    # keep separate for clarity, or add errors for existing/non-existing users?
    # also, should we add support for upserting list of users?
    raise_if_not_project_index_role(user, ix, Roles.ADMIN)
    update_project_role(email, ix, Roles[role])


@app_index_users.delete("/index/{ix}/users/{email}")
def remove_index_user(ix: IndexId, email: str, user: User = Depends(authenticated_user)):
    """
    Remove this user from the index.

    This requires ADMIN rights on the index or server, unless the user is removing themselves.
    """
    if user.email and user.email != email:
        raise_if_not_project_index_role(user, ix, Roles.ADMIN)
    delete_project_role(email, ix)
