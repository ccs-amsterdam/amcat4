import pytest
from elasticsearch import NotFoundError

from amcat4.models import AdminPermissionRequest, CreateProjectRequest, ProjectRoleRequest, Roles, User
from amcat4.systemdata.requests import (
    delete_request,
    list_admin_requests,
    list_all_requests,
    list_user_requests,
    process_request,
    update_request,
)
from amcat4.systemdata.roles import (
    create_project_role,
    delete_project_role,
    get_user_project_role,
    update_project_role,
    update_server_role,
)
from amcat4.systemdata.settings import get_project_settings


async def all_requests() -> dict[str, AdminPermissionRequest]:
    return {get_request_id(r): r async for r in list_all_requests()}


async def admin_requests(user: User) -> dict[str, AdminPermissionRequest]:
    return {get_request_id(r): r async for r in list_admin_requests(user)}


async def my_requests(user: User) -> dict[str, AdminPermissionRequest]:
    return {get_request_id(r): r async for r in list_user_requests(user)}


def get_request_id(r: AdminPermissionRequest) -> str:
    ## unique requests are identified by (type, email, index)
    d = r.model_dump()
    return request_id(d["request"]["type"], d["email"], d["request"].get("project_id"))


def request_id(type: str, email: str, project_id: str | None = None) -> str:
    return f"{type}:{project_id or ''}:{email}"


def requests_ids(requests):
    return set([request_id(r["request"]["type"], r["email"], r["request"].get("project_id")) for r in requests])


@pytest.mark.anyio
async def test_role_requests(clean_requests, index, user):
    assert await all_requests() == {}

    # Can we file a request?
    await update_request(
        AdminPermissionRequest(email=user, request=ProjectRoleRequest(type="project_role", project_id=index, role="ADMIN"))
    )

    requests = await all_requests()
    id = request_id("project_role", user, index)
    assert set(requests.keys()) == {id}
    r = requests[id]
    assert isinstance(r, AdminPermissionRequest)
    assert r.request.type == "project_role" and r.request.role == "ADMIN"
    assert r.timestamp is not None
    t = r.timestamp

    # Does re-filing the request update the timestamp
    await update_request(
        AdminPermissionRequest(email=user, request=ProjectRoleRequest(type="project_role", project_id=index, role="ADMIN"))
    )
    requests = await all_requests()
    assert set(requests.keys()) == {id}
    r = requests[id]
    assert isinstance(r, AdminPermissionRequest)
    assert r.request.type == "project_role" and r.request.role == "ADMIN"
    assert r.timestamp is not None
    assert r.timestamp > t

    # Updating a request
    await update_request(
        AdminPermissionRequest(
            email=user, request=ProjectRoleRequest(type="project_role", project_id=index, role="METAREADER")
        )
    )
    requests = await all_requests()

    assert set(requests.keys()) == {id}
    r = requests[id]
    assert isinstance(r, AdminPermissionRequest)
    assert r.request.type == "project_role" and r.request.role == "METAREADER"

    # Cancelling a request
    await delete_request(
        AdminPermissionRequest(
            email=user, request=ProjectRoleRequest(type="project_role", project_id=index, role="METAREADER")
        )
    )
    assert await all_requests() == {}


@pytest.mark.anyio
async def test_list_admin_requests(clean_requests, index, guest_index, index_name, user, admin):
    user_obj = User(email=user)

    assert await all_requests() == {}
    requests = await admin_requests(user_obj)
    assert requests == {}

    ## Make three requests
    await update_request(
        AdminPermissionRequest(
            email="john@example.com", request=ProjectRoleRequest(type="project_role", project_id=index, role="METAREADER")
        )
    )
    await update_request(
        AdminPermissionRequest(
            email="jane@example.com", request=ProjectRoleRequest(type="project_role", project_id=guest_index, role="ADMIN")
        )
    )
    await update_request(
        AdminPermissionRequest(
            email="john@example.com", request=CreateProjectRequest(type="create_project", project_id=index_name)
        )
    )
    ## create their ids (for ease of testing assertions)
    john_role_req = request_id("project_role", "john@example.com", index)
    jane_role_req = request_id("project_role", "jane@example.com", guest_index)
    john_create_req = request_id("create_project", "john@example.com", index_name)

    await update_request(
        AdminPermissionRequest(
            email="john@example.com", request=CreateProjectRequest(type="create_project", project_id=index_name)
        )
    )

    # An admin on a specific index should see requests for that index
    await create_project_role(user, index, Roles.ADMIN)

    requests = await admin_requests(user_obj)
    assert set(requests.keys()) == {john_role_req}

    await create_project_role(user, guest_index, Roles.ADMIN)
    requests = await admin_requests(user_obj)
    assert set(requests.keys()) == {john_role_req, jane_role_req}

    # A global writer can see project creation requests (???)
    await update_server_role(user, Roles.WRITER)
    await delete_project_role(user, guest_index)
    requests = await admin_requests(user_obj)
    assert set(requests.keys()) == {john_role_req, john_create_req}

    admin_obj = User(email=admin)
    requests = await admin_requests(admin_obj)

    assert set(requests.keys()) == {john_create_req}


@pytest.mark.anyio
async def test_list_my_requests(clean_requests, index, index_name, user):
    user_obj = User(email=user)

    assert [r async for r in list_user_requests(user_obj)] == []
    await update_request(
        AdminPermissionRequest(
            email="someoneelse@example.com", request=ProjectRoleRequest(type="project_role", project_id=index, role="ADMIN")
        )
    )
    assert [r async for r in list_user_requests(user_obj)] == []
    await update_request(
        AdminPermissionRequest(email=user, request=ProjectRoleRequest(type="project_role", project_id=index, role="ADMIN"))
    )
    user_role_req = request_id("project_role", user, index)

    requests = await my_requests(user_obj)
    assert set(requests.keys()) == {user_role_req}

    role_request = requests[user_role_req]
    assert role_request.request.type == "project_role"
    assert role_request.request.role == Roles.ADMIN.name

    await update_request(
        AdminPermissionRequest(email=user, request=CreateProjectRequest(type="create_project", project_id=index_name))
    )
    user_create_req = request_id("create_project", user, index_name)
    requests = await my_requests(user_obj)

    assert set(requests.keys()) == {user_role_req, user_create_req}


@pytest.mark.anyio
async def test_resolve_requests(clean_requests, index, index_name, user, admin):
    user_obj = User(email=user)
    admin_obj = User(email=admin)

    assert await all_requests() == {}
    assert (await get_user_project_role(user_obj, index)).role == Roles.NONE.name

    with pytest.raises(NotFoundError):
        await get_project_settings(index_name)

    await update_project_role(admin, index, Roles.ADMIN, ignore_missing=True)
    await update_request(
        AdminPermissionRequest(email=user, request=ProjectRoleRequest(type="project_role", project_id=index, role="ADMIN"))
    )
    await update_request(
        AdminPermissionRequest(email=user, request=CreateProjectRequest(type="create_project", project_id=index_name))
    )

    requests = [r async for r in list_admin_requests(admin_obj)]
    ## created 2 requests
    assert len(requests) == 2

    ## Update status and process request
    for request in requests:
        request.status = "approved"
        await process_request(request)

    assert (await get_user_project_role(user_obj, index)).role == Roles.ADMIN.name
    assert (await get_project_settings(index_name)).id == index_name

    ## Admins can no longer see the processed requests
    assert len([r async for r in list_admin_requests(admin_obj)]) == 0

    ## User that submitted them can see the updated status.
    ## Users can also delete requests (or cancel them by deleting before being processed)
    async for request in list_user_requests(user_obj):
        assert request.status == "approved"
        await delete_request(request)

    # Now all requests are gone
    assert len([r async for r in list_all_requests()]) == 0


@pytest.mark.anyio
async def test_project_attributes(clean_requests, index_name, user, admin):
    admin_obj = User(email=admin)
    await update_request(
        AdminPermissionRequest(
            email=user,
            request=CreateProjectRequest(project_id=index_name, name="name", message="message", type="create_project"),
        )
    )

    requests = [r async for r in list_admin_requests(admin_obj)]
    for request in requests:
        request.status = "approved"
        await process_request(request)

    assert (await get_project_settings(index_name)).name == "name"
