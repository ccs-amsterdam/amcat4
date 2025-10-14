from fastapi import APIRouter, Body, Depends, HTTPException, Response, status

from amcat4.api.auth import authenticated_user
from amcat4.index import GUEST_USER, Role
from amcat4.projectdata import list_user_project_indices
from amcat4.systemdata.requests import (
    PermissionRequest,
    elastic_create_or_update_request,
    elastic_list_admin_requests,
    elastic_list_user_requests,
    process_requests,
)
from amcat4.systemdata.roles import elastic_get_role, has_role

app_requests = APIRouter(tags=["requests"], prefix="/permission_requests")


@app_requests.get("/admin")
def get_admin_requests(user: str = Depends(authenticated_user)):
    # Not sure if guests should be banned, it might make sense in no_auth, but does it really?
    """Get all requests that this user can resolve"""
    if user == GUEST_USER:
        raise HTTPException(
            status_code=401,
            detail="Anonymous guests cannot check admin requests",
        )
    return elastic_list_admin_requests(email=user)


@app_requests.post("/admin", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def post_admin_requests(requests: list[PermissionRequest] = Body(...), user: str = Depends(authenticated_user)):
    """Resolve (approve, enact, and remove) the listed role requests"""
    # Adapted auth logic from ../requests.py, wasn't sure how to generalize this
    server_role = elastic_get_role(user, "_server")
    if server_role != Role.ADMIN:
        is_writer = has_role(user, "_server", "WRITER")
        admin_indices = {ix.id for (ix, role) in list_user_project_indices(user) if role == Role.ADMIN}
        for r in requests:
            if r.request_type == "create_project" and not is_writer:
                raise HTTPException(status_code=401, detail=f"User {user} is not a server WRITER, so cannot resolve {r}")
            if r.request_type == "role" and r.permission_context not in admin_indices:
                raise HTTPException(
                    status_code=401,
                    detail=f"User {user} is not admin on {r.permission_context} so cannot resolve role request {r}",
                )
    process_requests(requests)


@app_requests.get("/")
def get_requests(user: str = Depends(authenticated_user)):
    """Lists any active role request from this user"""
    if user == GUEST_USER:
        raise HTTPException(
            status_code=401,
            detail="Anonymous guests cannot have requests",
        )

    return elastic_list_user_requests(email=user)


@app_requests.post("/", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def post_requests(request: PermissionRequest, user: str = Depends(authenticated_user)):
    """Create a new request"""
    if user == GUEST_USER:
        raise HTTPException(
            status_code=401,
            detail="Anonymous guests cannot make access requests",
        )
    if user != request.email:
        raise HTTPException(
            status_code=401,
            detail="Request email does not match user",
        )
    elastic_create_or_update_request(request)
