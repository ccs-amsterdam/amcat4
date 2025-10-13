from datetime import datetime
from typing import Iterable

from amcat4.config import get_settings
from amcat4.elastic import es
from amcat4.models import PermissionRequest, RoleRequest, CreateProjectRequest
from amcat4.index import (
    GLOBAL_ROLES,
    Role,
    create_index,
    get_global_role,
    list_user_indices,
    set_global_role,
    set_role,
)

# Requests are (for now) either role requets or create project requests
# type + email + index should be unique


def request_from_elastic(d) -> PermissionRequest:
    match d["request_type"]:
        case "role":
            return RoleRequest(**d)
        case "create_project":
            return CreateProjectRequest(**d)
        case _:
            raise ValueError(f"Cannot parse request {d}")


def list_user_requests(email: str) -> Iterable[PermissionRequest]:
    """List all requests for this user"""
    return (r for r in list_all_requests() if r.email == email)


def list_admin_requests(email: str) -> Iterable[PermissionRequest]:
    """List all requests that this user can administrate"""
    u = get_global_role(email)
    if u == Role.ADMIN:
        return list_all_requests()
    admin_indices = {
        ix.id for (ix, role) in list_user_indices(email) if role == Role.ADMIN
    }
    return (
        r
        for r in list_all_requests()
        if (r.request_type == "create_project" and u == Role.WRITER)
        or (r.request_type == "role" and r.index in admin_indices)
    )


def list_all_requests() -> Iterable[PermissionRequest]:
    system_index = get_settings().system_index
    r = es().get(index=system_index, id=GLOBAL_ROLES, source=["requests"])
    for d in r["_source"].get("requests", []):
        yield request_from_elastic(d)


def create_request(request: PermissionRequest):
    """
    Create, update or cancel a request.
    """
    # TODO add timestamp=datetime.now().isoformat())
    # Index requests  by type+email+index
    if not request.timestamp:
        request.timestamp = datetime.now()
    requests = {(r.request_type, r.email, r.index): r for r in list_all_requests()}

    if request.cancel:
        del requests[request.request_type, request.email, request.index]
    else:
        # Overwrite existing or add new request on key
        requests[request.request_type, request.email, request.index] = request
    request_list = [r.model_dump() for r in requests.values()]
    es().update(
        index=get_settings().system_index,
        id=GLOBAL_ROLES,
        doc={"requests": request_list},
        refresh=True,
    )


def process_requests(requests: list[PermissionRequest]):
    all_requests = {(r.request_type, r.email, r.index): r for r in list_all_requests()}
    for r in requests:
        if not r.reject:
            match r.request_type:
                case "role":
                    assert isinstance(r, RoleRequest)
                    process_role_request(r)
                case "create_project":
                    assert isinstance(r, CreateProjectRequest)
                    process_project_request(r)
                case _:
                    raise ValueError(f"Cannot process {r}")
        # Remove the request from the pending requests
        all_requests.pop((r.request_type, r.email, r.index), None)
    # Update requests list in elastic
    request_list = [r.model_dump() for r in all_requests.values()]
    es().update(
        index=get_settings().system_index,
        id=GLOBAL_ROLES,
        doc={"requests": request_list},
        refresh=True,
    )


def process_role_request(r: RoleRequest):
    desired_role = None if r.role == "NONE" else Role[r.role.upper()]
    if r.index:
        set_role(r.index, r.email, desired_role)
    else:
        set_global_role(r.email, desired_role)


def process_project_request(r: CreateProjectRequest):
    create_index(
        r.index, admin=r.email, name=r.name, description=r.description, folder=r.folder
    )


def clear_requests():
    es().update(
        index=get_settings().system_index,
        id=GLOBAL_ROLES,
        doc={"requests": []},
        refresh=True,
    )
