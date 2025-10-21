from fastapi import APIRouter, Body, Depends, HTTPException, Response, status

from amcat4.api.auth import authenticated_user
from amcat4.models import PermissionRequest, Roles, User
from amcat4.systemdata.requests import (
    update_request,
    list_admin_requests,
    list_user_requests,
    process_request,
)
from amcat4.systemdata.roles import raise_if_not_project_index_role

app_requests = APIRouter(tags=["requests"], prefix="/permission_requests")


@app_requests.get("/admin")
def get_admin_requests(user: User = Depends(authenticated_user)):
    # Not sure if guests should be banned, it might make sense in no_auth, but does it really?
    """Get all requests that this user can resolve"""

    return list_admin_requests(user=user)


@app_requests.post("/admin", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def post_admin_requests(requests: list[PermissionRequest] = Body(...), user: User = Depends(authenticated_user)):
    """Resolve (approve, enact, and remove) the listed role requests"""

    for r in requests:
        if r.request_type == "create_project":
            raise_if_not_project_index_role(user, "_server", Roles.WRITER)
        if r.request_type == "role":
            raise_if_not_project_index_role(user, r.role_context, Roles.ADMIN)

        process_request(r)


@app_requests.get("/")
def get_requests(user: User = Depends(authenticated_user)):
    """Lists any active role request from this user"""
    return list_user_requests(user=user)


@app_requests.post("/", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def post_requests(request: PermissionRequest, user: User = Depends(authenticated_user)):
    """Create a new request"""
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
    update_request(request)
