"""API Endpoints for managing permission requests."""

from typing import Annotated

from elasticsearch import NotFoundError
from fastapi import APIRouter, Body, Depends, HTTPException, status

from amcat4.api.auth import authenticated_user
from amcat4.models import AdminPermissionRequest, PermissionRequest, Roles, User
from amcat4.systemdata.requests import (
    delete_request,
    list_admin_requests,
    list_user_requests,
    process_request,
    update_request,
)
from amcat4.systemdata.roles import (
    HTTPException_if_not_project_index_role,
    get_user_server_role,
    role_is_at_least,
)

app_requests = APIRouter(tags=["requests"], prefix="/permission_requests")


@app_requests.get("/admin")
async def get_admin_requests(user: User = Depends(authenticated_user)) -> list[AdminPermissionRequest]:
    """
    Get all requests that this user can resolve.
    Server and project ADMINs can resolve role requests.
    Server ADMINs and WRITERs can resolve project creation requests.
    """
    return [r async for r in list_admin_requests(user=user)]


@app_requests.post("/admin", status_code=status.HTTP_204_NO_CONTENT)
async def post_admin_requests(requests: list[AdminPermissionRequest] = Body(...), user: User = Depends(authenticated_user)):
    """Resolve (approve, enact, and remove) the listed role requests. Requires appropriate admin/writer roles."""
    server_role = await get_user_server_role(user)

    for r in requests:
        if r.request.type == "create_project":
            if not role_is_at_least(server_role, Roles.WRITER):
                raise HTTPException(
                    status_code=403,
                    detail="Only server WRITERs and ADMINs can process project creation requests",
                )
        if r.request.type == "server_role":
            if not role_is_at_least(server_role, Roles.ADMIN):
                raise HTTPException(
                    status_code=403,
                    detail="Only server ADMINs can process server role requests",
                )
        if r.request.type == "project_role":
            await HTTPException_if_not_project_index_role(
                user, r.request.project_id, Roles.ADMIN, message="Only project ADMINs can process project role requests"
            )

        try:
            await process_request(r)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Error processing request {r.request.type} for {r.email}: {e}",
            )


@app_requests.get("", response_model=list[AdminPermissionRequest])
async def get_my_requests(user: User = Depends(authenticated_user)):
    """Lists any active role request from this user."""
    if user.email is None:
        raise HTTPException(401, detail="Anonymous guests have no permission requests.")
    return [r async for r in list_user_requests(user=user)]


@app_requests.post("", status_code=status.HTTP_204_NO_CONTENT)
async def post_requests(request: Annotated[PermissionRequest, Body(...)], user: User = Depends(authenticated_user)):
    """Create a new permission request. The user must be authenticated."""
    if user.email is None:
        raise HTTPException(
            status_code=401,
            detail="Anonymous guests cannot make access requests",
        )

    await update_request(AdminPermissionRequest(email=user.email, request=request))


@app_requests.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_request(request: Annotated[PermissionRequest, Body(...)], user: User = Depends(authenticated_user)):
    """Delete an existing permission request. The user must be authenticated."""
    if user.email is None:
        raise HTTPException(
            status_code=401,
            detail="You can only delete your own requests as an authenticated user",
        )
    try:
        ## authentication is implicit, because users can only delete their own requests
        await delete_request(AdminPermissionRequest(email=user.email, request=request))
    except NotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Request not found",
        )
