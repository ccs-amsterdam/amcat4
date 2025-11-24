from typing import AsyncIterable

from amcat4.connections import es
from amcat4.elastic.util import index_scan
from amcat4.models import (
    AdminPermissionRequest,
    CreateProjectRequest,
    ProjectRoleRequest,
    ProjectSettings,
    Roles,
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
from amcat4.systemdata.versions import requests_index_id, requests_index_name


async def update_request(request: AdminPermissionRequest):
    # TODO add timestamp=datetime.now().isoformat())
    # Index requests  by type+email+index
    doc = _request_to_elastic(request)
    id = requests_index_id(doc.get("type"), doc.get("email"), doc.get("project_id", None))
    await es().update(
        index=requests_index_name(),
        id=id,
        doc=doc,
        doc_as_upsert=True,
        refresh=True,
    )


async def delete_request(request: AdminPermissionRequest):
    doc = _request_to_elastic(request)
    id = requests_index_id(doc["type"], doc["email"], doc["project_id"])
    await es().delete(index=requests_index_name(), id=id, refresh=True)


async def list_user_requests(user: User) -> AsyncIterable[AdminPermissionRequest]:
    """List all requests for this user"""
    if user.email is None:
        return

    docs = index_scan(requests_index_name(), query={"term": {"email": user.email}})
    async for id, doc in docs:
        yield _request_from_elastic(doc)


async def list_admin_requests(user: User) -> AsyncIterable[AdminPermissionRequest]:
    """
    List all requests that this user can administrate.
    - For role requests, this means having ADMIN role on the relevant context.
    - For create_project requests, this means having WRITER role on the _server context.
    - only returns pending requests
    """
    if user.email is None:
        return

    server_role = await get_user_server_role(user)

    # Create project requests
    if role_is_at_least(server_role, Roles.WRITER):
        query = {"bool": {"must": [{"term": {"type": "create_project"}}, {"term": {"status": "pending"}}]}}
        async for id, doc in index_scan(requests_index_name(), query=query):
            yield _request_from_elastic(doc)

    # Server role requests
    if role_is_at_least(server_role, Roles.ADMIN):
        query = {"bool": {"must": [{"term": {"type": "server_role"}}, {"term": {"status": "pending"}}]}}
        async for id, doc in index_scan(requests_index_name(), query=query):
            yield _request_from_elastic(doc)

    # Project role requests
    roles = await list_user_project_roles(user, required_role=Roles.ADMIN)
    if roles:
        query = {
            "bool": {
                "must": [
                    {"terms": {"project_id": [r.role_context for r in roles]}},
                    {"terms": {"type": ["server_role", "project_role"]}},
                    {"term": {"status": "pending"}},
                ]
            }
        }

        async for id, doc in index_scan(requests_index_name(), query=query):
            yield _request_from_elastic(doc)


async def process_request(request: AdminPermissionRequest):
    if request.status == "pending":
        return None
    elif request.status == "approved":
        await _approve_request(request)
    elif request.status == "rejected":
        pass
    else:
        raise ValueError(f"Unknown request status {request.status}")

    await update_request(request)


async def _approve_request(ar: AdminPermissionRequest):
    match ar.request.type:
        case "server_role":
            await update_server_role(ar.email, Roles[ar.request.role], ignore_missing=True)
        case "project_role":
            assert isinstance(ar.request, ProjectRoleRequest)
            await update_project_role(ar.email, ar.request.project_id, Roles[ar.request.role], ignore_missing=True)
        case "create_project":
            assert isinstance(ar.request, CreateProjectRequest)
            new_index = ProjectSettings(
                id=ar.request.project_id,
                name=ar.request.name,
                description=ar.request.description,
                folder=ar.request.folder,
            )
            await create_project_index(new_index, admin_email=ar.email)


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


async def clear_requests():
    """
    TEST ONLY!!
    """
    await (es()).delete_by_query(index=requests_index_name(), query={"match_all": {}}, refresh=True)


async def list_all_requests(statuses: list[str] | None = None) -> AsyncIterable[AdminPermissionRequest]:
    """
    TESTS ONLY
    """
    query = {"terms": {"status": statuses}} if statuses else {"match_all": {}}

    async for id, doc in index_scan(requests_index_name(), query=query):
        yield _request_from_elastic(doc)
