"""API Endpoints for document and index management."""

from fastapi import APIRouter, Body, Depends, status, Path
from pydantic import BaseModel, Field

from amcat4.api.auth import authenticated_user
from amcat4.models import (
    IndexId,
    RoleEmailPattern,
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
    email: RoleEmailPattern = Field(
        ...,
        description="The closest email address the user matches to. Can be an exact email address (user@domain.com), domain wildcard (*@domain.com) or guest wildcard (*)",
    )
    role: Role = Field(..., description="The user role associate to this email address, domain or guest")


@app_index_users.get("/index/{ix}/users")
def list_index_users(
    ix: IndexId = Path(..., description="ID of the index to list users for"), user: User = Depends(authenticated_user)
) -> list[IndexUserResponse]:
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
    ix: IndexId = Path(..., description="ID of the index to add the user to"),
    email: RoleEmailPattern = Body(..., description="Email address of the user to add"),
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
    ix: IndexId = Path(..., description="ID of the index to modify the user in"),
    email: RoleEmailPattern = Path(..., description="Email address of the user to modify"),
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
def remove_index_user(
    ix: IndexId = Path(..., description="ID of the index to remove the user from"),
    email: RoleEmailPattern = Path(..., description="Email address of the user to remove"),
    user: User = Depends(authenticated_user),
):
    """
    Remove this user from the index.

    This requires ADMIN rights on the index or server, unless the user is removing themselves.
    """
    if user.email != email:
        raise_if_not_project_index_role(user, ix, Roles.ADMIN)
    delete_project_role(email, ix)
