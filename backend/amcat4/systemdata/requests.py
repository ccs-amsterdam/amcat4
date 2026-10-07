from typing import AsyncIterable

from psycopg.types.json import Jsonb

from amcat4.errors import NotFoundError
from amcat4.models import (
    AdminPermissionRequest,
    CreateProjectRequest,
    ProjectRoleRequest,
    ProjectSettings,
    Roles,
    User,
)
from amcat4.postgres.connection import execute, fetch_all, fetch_one
from amcat4.projects.index import create_project_index
from amcat4.systemdata.roles import (
    get_user_server_role,
    list_user_project_roles,
    role_is_at_least,
    update_project_role,
    update_server_role,
)


async def _keys(request: AdminPermissionRequest) -> tuple[int | None, str | None]:
    """The project pk (for project role requests) and new project id (for create project requests)"""
    if isinstance(request.request, ProjectRoleRequest):
        row = await fetch_one("SELECT pk FROM projects WHERE id = %s", [request.request.project_id])
        if row is None:
            raise NotFoundError(f"Project {request.request.project_id} does not exist")
        return row["pk"], None
    if isinstance(request.request, CreateProjectRequest):
        return None, request.request.project_id
    return None, None


async def update_request(request: AdminPermissionRequest):
    """Create or update a request. Requests are identified by type, email and project"""
    project_pk, new_project_id = await _keys(request)
    await execute(
        """INSERT INTO requests (type, email, project_pk, new_project_id, status, timestamp, request)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (type, email, coalesce(project_pk, 0), coalesce(new_project_id, '')) DO UPDATE
           SET status = EXCLUDED.status, timestamp = EXCLUDED.timestamp, request = EXCLUDED.request""",
        [
            request.request.type,
            request.email,
            project_pk,
            new_project_id,
            request.status,
            request.timestamp,
            Jsonb(request.request.model_dump(mode="json")),
        ],
    )


async def delete_request(request: AdminPermissionRequest):
    project_pk, new_project_id = await _keys(request)
    n = await execute(
        """DELETE FROM requests WHERE type = %s AND email = %s AND coalesce(project_pk, 0) = coalesce(%s, 0)
           AND coalesce(new_project_id, '') = coalesce(%s, '')""",
        [request.request.type, request.email, project_pk, new_project_id],
    )
    if n == 0:
        raise NotFoundError("Request does not exist")


async def _list_requests(where: str = "TRUE", params: list | None = None) -> list[AdminPermissionRequest]:
    rows = await fetch_all(
        f"SELECT email, status, timestamp, request FROM requests WHERE {where} ORDER BY timestamp",  # type: ignore[arg-type]
        params,
    )
    return [AdminPermissionRequest.model_validate(row) for row in rows]


async def list_user_requests(user: User) -> AsyncIterable[AdminPermissionRequest]:
    """List all requests for this user"""
    if user.email is None:
        return
    for request in await _list_requests("email = %s", [user.email]):
        yield request


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
    if role_is_at_least(user, server_role, Roles.WRITER):
        for request in await _list_requests("type = 'create_project' AND status = 'pending'"):
            yield request

    # Server role requests
    if role_is_at_least(user, server_role, Roles.ADMIN):
        for request in await _list_requests("type = 'server_role' AND status = 'pending'"):
            yield request

    # Project role requests
    roles = await list_user_project_roles(user, required_role=Roles.ADMIN)
    if roles:
        projects = [r.role_context for r in roles]
        for request in await _list_requests(
            "type = 'project_role' AND status = 'pending' AND project_pk IN (SELECT pk FROM projects WHERE id = ANY(%s))",
            [projects],
        ):
            yield request


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


# ================================ USED IN TESTS ONLY =========================================


async def clear_requests():
    """
    TEST ONLY!!
    """
    await execute("DELETE FROM requests")


async def list_all_requests(statuses: list[str] | None = None) -> AsyncIterable[AdminPermissionRequest]:
    """
    TESTS ONLY
    """
    requests = await _list_requests("status = ANY(%s)", [statuses]) if statuses else await _list_requests()
    for request in requests:
        yield request
