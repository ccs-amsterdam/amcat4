"""API Endpoints for project user management."""

from fastapi import APIRouter, Body, Depends, Path, Response, status
from pydantic import BaseModel, Field

from amcat4.api.auth import authenticated_user
from amcat4.models import (
    IndexId,
    Role,
    RoleEmailPattern,
    Roles,
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


# REQUEST MODELS
class AddIndexUserBody(BaseModel):
    """Body for adding a user to an index."""

    email: RoleEmailPattern = Field(..., description="Email address of the user to add.")
    role: Role = Field(..., description="Role to grant to the user.")


# RESPONSE MODELS
class IndexUserResponse(BaseModel):
    """Response for an index user."""

    email: RoleEmailPattern = Field(
        ...,
        description="The email pattern for this role (e.g., user@example.com, *@example.com, or *).",
    )
    role: Role = Field(..., description="The role assigned to the user.")


@app_index_users.get("/index/{ix}/users")
def list_index_users(
    ix: IndexId = Path(..., description="ID of the index to list users for"), user: User = Depends(authenticated_user)
) -> list[IndexUserResponse]:
    """
    List the users and their roles for a given index. Requires WRITER role on the index.
    """
    raise_if_not_project_index_role(user, ix, Roles.WRITER)
    roles = list_project_roles(project_ids=[ix])
    return [IndexUserResponse(email=r.email, role=r.role) for r in roles]


@app_index_users.post("/index/{ix}/users", status_code=status.HTTP_201_CREATED)
def add_index_user(
    ix: IndexId = Path(..., description="ID of the index to add the user to"),
    body: AddIndexUserBody = Body(...),
    user: User = Depends(authenticated_user),
) -> IndexUserResponse:
    """
    Add a user to an index or update their role. Requires ADMIN role on the index.
    """
    raise_if_not_project_index_role(user, ix, Roles.ADMIN)
    create_project_role(body.email, ix, Roles[body.role])
    return IndexUserResponse(email=body.email, role=body.role)


@app_index_users.put("/index/{ix}/users/{email}", status_code=status.HTTP_200_OK)
def modify_index_user(
    ix: IndexId = Path(..., description="ID of the index to modify the user in"),
    email: RoleEmailPattern = Path(..., description="Email address of the user to modify"),
    role: Role = Body(..., description="New role for the user", embed=True),
    user: User = Depends(authenticated_user),
) -> IndexUserResponse:
    """
    Change the role of a user in an index. Requires ADMIN role on the index.
    """
    raise_if_not_project_index_role(user, ix, Roles.ADMIN)
    update_project_role(email, ix, Roles[role])
    return IndexUserResponse(email=email, role=role)


@app_index_users.delete("/index/{ix}/users/{email}", status_code=status.HTTP_204_NO_CONTENT)
def remove_index_user(
    ix: IndexId = Path(..., description="ID of the index to remove the user from"),
    email: RoleEmailPattern = Path(..., description="Email address of the user to remove"),
    user: User = Depends(authenticated_user),
):
    """
    Remove a user from an index. Requires ADMIN role on the index, unless a user is removing themselves.
    """
    if user.email != email:
        raise_if_not_project_index_role(user, ix, Roles.ADMIN)
    delete_project_role(email, ix)
