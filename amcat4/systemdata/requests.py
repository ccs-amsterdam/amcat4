from typing import Iterable


from amcat4.elastic import es
from amcat4.models import (
    AdminPermissionRequest,
    ProjectRoleRequest,
    ProjectSettings,
    Roles,
    CreateProjectRequest,
    User,
)
from amcat4.projects.index import create_project_index
from amcat4.systemdata.roles import (
    get_user_server_role,
    list_user_project_roles,
    role_is_at_least,
    update_project_role,
    update_server_role,
)
from amcat4.elastic.util import index_scan
from amcat4.systemdata.versions import requests_index, requests_index_id


def update_request(request: AdminPermissionRequest):
    # TODO add timestamp=datetime.now().isoformat())
    # Index requests  by type+email+index
    doc = _request_to_elastic(request)
    id = requests_index_id(doc.get("type"), doc.get("email"), doc.get("project_id", None))

    es().update(
        index=requests_index(),
        id=id,
        doc=doc,
        doc_as_upsert=True,
        refresh=True,
    )


def delete_request(request: AdminPermissionRequest):
    doc = _request_to_elastic(request)
    id = requests_index_id(doc["type"], doc["email"], doc["project_id"])
    es().delete(index=requests_index(), id=id, refresh=True)


def list_user_requests(user: User) -> Iterable[AdminPermissionRequest]:
    """List all requests for this user"""
    if user.email is None:
        return []

    docs = index_scan(requests_index(), query={"term": {"email": user.email}})
    for id, doc in docs:
        yield _request_from_elastic(doc)


def list_admin_requests(user: User) -> Iterable[AdminPermissionRequest]:
    """
    List all requests that this user can administrate.
    - For role requests, this means having ADMIN role on the relevant context.
    - For create_project requests, this means having WRITER role on the _server context.
    - only returns pending requests
    """
    if user.email is None:
        return []

    server_role = get_user_server_role(user)

    # Create project requests
    if role_is_at_least(server_role, Roles.WRITER):
        query = {"bool": {"must": [{"term": {"type": "create_project"}}, {"term": {"status": "pending"}}]}}
        for id, doc in index_scan(requests_index(), query=query):
            yield _request_from_elastic(doc)

    # Server role requests
    if role_is_at_least(server_role, Roles.ADMIN):
        query = {"bool": {"must": [{"term": {"type": "server_role"}}, {"term": {"status": "pending"}}]}}
        for id, doc in index_scan(requests_index(), query=query):
            yield _request_from_elastic(doc)

    # Project role requests
    role_contexts = [r.role_context for r in list_user_project_roles(user, required_role=Roles.ADMIN)]
    if role_contexts:
        query = {
            "bool": {
                "must": [
                    {"terms": {"project_id": role_contexts}},
                    {"terms": {"type": ["server_role", "project_role"]}},
                    {"term": {"status": "pending"}},
                ]
            }
        }

        for id, doc in index_scan(requests_index(), query=query):
            yield _request_from_elastic(doc)


def process_request(request: AdminPermissionRequest):
    if request.status == "pending":
        return None
    elif request.status == "approved":
        _approve_request(request)
    elif request.status == "rejected":
        pass
    else:
        raise ValueError(f"Unknown request status {request.status}")

    update_request(request)


def _approve_request(ar: AdminPermissionRequest):
    match ar.request.type:
        case "server_role":
            update_server_role(ar.email, Roles[ar.request.role], ignore_missing=True)
        case "project_role":
            assert isinstance(ar.request, ProjectRoleRequest)
            update_project_role(ar.email, ar.request.project_id, Roles[ar.request.role], ignore_missing=True)
        case "create_project":
            assert isinstance(ar.request, CreateProjectRequest)
            new_index = ProjectSettings(
                id=ar.request.project_id,
                name=ar.request.name,
                description=ar.request.description,
                folder=ar.request.folder,
            )
            create_project_index(new_index, admin_email=ar.email)


def _request_to_elastic(request: AdminPermissionRequest) -> dict:
    # Almost the same, just flattened
    # TODO: maybe make system index identical to model structure
    doc = dict(
        email=request.email,
        timestamp=request.timestamp,
        status=request.status,
        **request.request.model_dump(),
    )

    doc = {k: v for k, v in doc.items() if v is not None}
    return doc


def _request_from_elastic(d: dict) -> AdminPermissionRequest:
    return AdminPermissionRequest.model_validate(
        dict(
            email=d.get("email"),
            timestamp=d.get("timestamp"),
            status=d.get("status"),
            request=d,
        )
    )


# ================================ USED IN TESTS ONLY =========================================


def clear_requests():
    """
    TEST ONLY!!
    """
    es().delete_by_query(index=requests_index(), query={"match_all": {}}, refresh=True)


def list_all_requests(statuses: list[str] | None = None) -> Iterable[AdminPermissionRequest]:
    """
    TESTS ONLY
    """
    query = {"terms": {"status": statuses}} if statuses else {"match_all": {}}

    for id, doc in index_scan(requests_index(), query=query):
        yield _request_from_elastic(doc)
