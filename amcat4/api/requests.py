from fastapi import APIRouter, Depends, HTTPException, Response, status

from amcat4.api.auth import authenticated_user, check_global_role, check_role
from amcat4.index import GUEST_USER, Role
from amcat4.requests import RoleRequest, get_role_requests, set_role_request

from .index import app_index
from .users import app_users

app_requests = APIRouter(tags=["requests"])


@app_requests.get("/role_requests")
def get_global_role_requests(user: str = Depends(authenticated_user)):
    check_global_role(user, Role.ADMIN)
    return get_role_requests(user=user)


@app_requests.post("/role_requests", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def post_global_role_requests(
    request: RoleRequest,
    user: str = Depends(authenticated_user),
):
    """Resolve the listed role requests"""
    if user == GUEST_USER:
        raise HTTPException(
            status_code=401,
            detail="Anonymous guests cannot make access requests",
        )

    role = None if request.role == "NONE" else Role[request.role]
    set_role_request(index=None, email=user, role=role)


@app_requests.get("/index/{ix}/role_requests")
def get_index_role_requests(ix: str, user: str = Depends(authenticated_user)):
    check_role(user, Role.ADMIN, ix)
    return get_role_requests(ix)


@app_requests.post("/index/{ix}/role_requests", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def post_index_role_requests(
    ix: str,
    request: RoleRequest,
    user: str = Depends(authenticated_user),
):
    if user == GUEST_USER:
        raise HTTPException(
            status_code=401,
            detail="Anonymous guests cannot make access requests",
        )

    role = None if request.role == "NONE" else Role[request.role]
    set_role_request(ix, user, role)
