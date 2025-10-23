"""API Endpoints for managing permission requests."""

from typing import Annotated, Literal, Union
from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field

from amcat4.api.auth import authenticated_user
from amcat4.models import IndexId, PermissionRequest, Role, RoleContext, Roles, User
from amcat4.systemdata.requests import (
    update_request,
    list_admin_requests,
    list_user_requests,
    process_request,
)
from amcat4.systemdata.roles import raise_if_not_project_index_role

app_requests = APIRouter(tags=["requests"], prefix="/permission_requests")


## TODO: what should client facing requests look like?
# - maybe separate requests for server and project role


class PostRoleRequestBody(BaseModel):
    """Body for posting permission requests."""

    request_type: Literal["role"]
    role_context: RoleContext = Field(..., description="Where you are requesting the role for. Can be ")
    role: Role


class PostCreateProjectRequestBody(BaseModel):
    """Body for posting create project requests."""

    request_type: Literal["create_project"]
    project_id: IndexId = Field(..., description="ID for the new project.")
    name: str | None = Field(None, description="Optional name for the new project.")
    description: str | None = Field(None, description="Optional description for the new project.")
    folder: str | None = Field(None, description="Optional folder for the new project.")


class PostRequestBody(BaseModel):
    email: EmailStr = Field(..., description="Email address of the user making the request.")
    message: str | None = Field(None, description="Optional message from the user making the request.")
    request: Union[PostRoleRequestBody, PostCreateProjectRequestBody] = Field(
        discriminator="request_type", description="The permission request."
    )


class PostAdminRequestBody(BaseModel):
    decision: Literal["approve", "reject"] = Field(..., description="Decision on the request.")
    request: Annotated[PostRequestBody, Field(..., description="The permission request to process.")]


@app_requests.get("/admin")
def get_admin_requests(user: User = Depends(authenticated_user)) -> list[PermissionRequest]:
    """Get all requests that this user can resolve. Requires appropriate admin/writer roles."""
    return list_admin_requests(user=user)


@app_requests.post("/admin", status_code=status.HTTP_204_NO_CONTENT)
def post_admin_requests(requests: list[PermissionRequest] = Body(...), user: User = Depends(authenticated_user)):
    """Resolve (approve, enact, and remove) the listed role requests. Requires appropriate admin/writer roles."""
    for r in requests:
        if r.request_type == "create_project":
            raise_if_not_project_index_role(user, "_server", Roles.WRITER)
        if r.request_type == "role":
            raise_if_not_project_index_role(user, r.role_context, Roles.ADMIN)

        process_request(r)


@app_requests.get("/", response_model=list[PermissionRequest])
def get_requests(user: User = Depends(authenticated_user)):
    """Lists any active role request from this user."""
    return list_user_requests(user=user)


@app_requests.post("/", status_code=status.HTTP_204_NO_CONTENT)
def post_requests(request: Annotated[PostRequestBody, Body(...)], user: User = Depends(authenticated_user)):
    """Create a new permission request. The user must be authenticated."""
    if user.email is None:
        raise HTTPException(
            status_code=401,
            detail="Anonymous guests cannot make access requests",
        )
    if user.email != request.email:
        raise HTTPException(
            status_code=401,
            detail="Request email does not match user",
        )

    request_obj = request.request
    if request_obj.request_type == "create_project":
        request_obj.role_context = request_obj.project_id

    update_request(PermissionRequest(email=request.email, message=request.message, **request_obj))
