from fastapi import APIRouter, Body, Depends, HTTPException, Response, status

from amcat4.api.auth import authenticated_user, check_global_role
from amcat4.index import GUEST_USER, Role, get_global_role, list_user_indices
from amcat4.requests import (
    PermissionRequest,
    create_request,
    list_admin_requests,
    list_user_requests,
    process_requests,
)

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
    return list_admin_requests(email=user)


@app_requests.post("/admin", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def post_admin_requests(requests: list[PermissionRequest] = Body(...), user: str = Depends(authenticated_user)):
    """Resolve (approve, enact, and remove) the listed role requests"""
    # Adapted auth logic from ../requests.py, wasn't sure how to generalize this
    server_role = get_global_role(user)
    if server_role != Role.ADMIN:
        is_writer = bool(check_global_role(user, Role.WRITER, raise_error=False))
        admin_indices = {ix.id for (ix, role) in list_user_indices(user) if role == Role.ADMIN}
        for r in requests:
            if r.request_type == "create_project" and not is_writer:
                raise HTTPException(status_code=401, detail=f"User {user} is not a server WRITER, so cannot resolve {r}")
            if r.request_type == "role" and r.index not in admin_indices:
                raise HTTPException(
                    status_code=401, detail=f"User {user} is not admin on {r.index} so cannot resolve role request {r}"
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

    return list_user_requests(email=user)


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
    create_request(request)
