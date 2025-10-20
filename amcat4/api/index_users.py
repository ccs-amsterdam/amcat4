"""API Endpoints for document and index management."""

from fastapi import APIRouter, Body, Depends, status

from amcat4.api.auth import authenticated_user
from amcat4.models import (
    Roles,
    Role,
    User,
    RoleRule,
)
from amcat4.systemdata.roles import (
    create_project_role,
    delete_project_role,
    list_project_roles,
    raise_if_not_project_index_role,
    update_project_role,
)

app_index_users = APIRouter(prefix="/index/{ix}/users", tags=["project users"])


@app_index_users.get("")
def list_index_users(ix: str, user: User = Depends(authenticated_user)) -> list[RoleRule]:
    """
    List the users in this index.

    Allowed for global admin and local writers

    TODO: This used to be accessible to readers as well, but that doesn't seem
          right. Maybe we should even restrict to WRITERS (or READERS) that have an exact match?
    """
    raise_if_not_project_index_role(user, ix, Roles.WRITER)
    return list(list_project_roles(project_ids=[ix]))


@app_index_users.post("", status_code=status.HTTP_201_CREATED)
def add_index_users(
    ix: str,
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
    return {"user": email, "index": ix, "role": role}


@app_index_users.put("/{email}")
def modify_index_user(
    ix: str,
    email: str,
    role: Roles = Body(..., description="New role for the user", embed=True),
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
    update_project_role(email, ix, role)
    return {"user": email, "index": ix, "role": role}


@app_index_users.delete("/{email}")
def remove_index_user(ix: str, email: str, user: User = Depends(authenticated_user)):
    """
    Remove this user from the index.

    This requires ADMIN rights on the index or server
    """
    raise_if_not_project_index_role(user, ix, Roles.ADMIN)
    delete_project_role(email, ix)
    return {"user": email, "index": ix, "role": None}
