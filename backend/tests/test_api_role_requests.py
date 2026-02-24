import pytest
from elasticsearch import NotFoundError

from amcat4.models import AdminPermissionRequest, Roles, User
from amcat4.systemdata.requests import (
    list_admin_requests,
    list_all_requests,
    list_user_requests,
)
from amcat4.systemdata.roles import (
    create_project_role,
    get_user_project_role,
    update_project_role,
    update_server_role,
)
from amcat4.systemdata.settings import get_project_settings
from tests.tools import auth_cookie, check, get_json, post_json


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
async def test_api_request_attributes(clean_requests, client, index_name, user):
    request = dict(type="create_project", message="message", name="name", project_id=index_name)
    await post_json(client, "/permission_requests", json=request, user=user, expected=204)
    r = await get_json(client, "/permission_requests", user=user)
    assert len(r) == 1
    assert r[0]["request"]["message"] == "message"
    assert r[0]["request"]["name"] == "name"


@pytest.mark.anyio
async def test_api_post_request(clean_requests, client, index, index_name, user):
    assert await all_requests() == {}
    user_role_req = dict(type="project_role", project_id=index, role="ADMIN")
    user_proj_req = dict(type="create_project", project_id=index_name)
    user_role_id = request_id("project_role", user, index)
    user_proj_id = request_id("create_project", user, index_name)

    # Guests / unauthenticated users cannot post requests
    await check(await client.post("/permission_requests", json=user_role_req), expected=401)
    # Can we post role and project requests?
    await post_json(
        client,
        "/permission_requests",
        expected=204,
        json=user_role_req,
        user=user,
    )
    assert set((await all_requests()).keys()) == {user_role_id}
    await post_json(
        client,
        "/permission_requests",
        expected=204,
        json=user_proj_req,
        user=user,
    )
    assert set((await all_requests()).keys()) == {user_role_id, user_proj_id}


@pytest.mark.anyio
async def test_api_get_my_requests(clean_requests, client, index, user):
    assert await all_requests() == {}
    await check(await client.get("/permission_requests"), expected=401)
    assert await get_json(client, "/permission_requests", user=user) == []
    await post_json(
        client,
        "/permission_requests",
        user=user,
        json=dict(type="project_role", message="test", project_id=index, role="ADMIN"),
        expected=204,
    )
    (req,) = await get_json(client, "/permission_requests", user=user)
    assert req["request"]["type"] == "project_role"
    assert req["request"]["role"] == "ADMIN"
    assert req["email"] == user
    await post_json(
        client,
        "/permission_requests",
        user=user,
        json=dict(type="project_role", project_id=index, role="METAREADER"),
        expected=204,
    )
    (req,) = await get_json(client, "/permission_requests", user=user)
    assert req["request"]["type"] == "project_role"
    assert req["request"]["role"] == "METAREADER"
    assert req["email"] == user


@pytest.mark.anyio
async def test_api_get_admin_requests(clean_requests, client, guest_index, index, index_name, user, reader):
    assert await all_requests() == {}
    project_req = dict(type="create_project", project_id=index_name)
    index_admin_req = dict(type="project_role", project_id=index, role="ADMIN")
    guest_admin_req = dict(type="project_role", project_id=guest_index, role="ADMIN")
    server_admin_req = dict(type="server_role", role="WRITER")
    project_req_id = request_id("create_project", user, index_name)
    index_admin_req_id = request_id("project_role", user, index)
    server_admin_req_id = request_id("server_role", user, None)

    await post_json(client, "/permission_requests", expected=204, user=user, json=project_req)
    await post_json(client, "/permission_requests", expected=204, user=user, json=index_admin_req)
    await post_json(client, "/permission_requests", expected=204, user=user, json=guest_admin_req)
    await post_json(client, "/permission_requests", expected=204, user=user, json=server_admin_req)

    # server READER (i.e. no server role) can see no requests
    assert await get_json(client, "/permission_requests/admin", user=reader) == []
    # server WRITER can see project creation requests
    await update_server_role(reader, Roles.WRITER)
    assert requests_ids(await get_json(client, "/permission_requests/admin", user=reader)) == {project_req_id}
    # project WRITERS cannot see project role requests
    await create_project_role(reader, index, Roles.WRITER)
    assert requests_ids(await get_json(client, "/permission_requests/admin", user=reader)) == {project_req_id}
    # project ADMINs can see project role requests, but only for their own projects
    await update_project_role(reader, index, Roles.ADMIN)
    assert requests_ids(await get_json(client, "/permission_requests/admin", user=reader)) == {
        project_req_id,
        index_admin_req_id,
    }
    # Server admins can see server role requests. They DO NOT see project role requests unless they are also project admins
    await update_server_role(reader, Roles.ADMIN)
    assert requests_ids(await get_json(client, "/permission_requests/admin", user=reader)) == {
        project_req_id,
        index_admin_req_id,
        server_admin_req_id,
    }


@pytest.mark.anyio
async def test_api_post_admin_requests(clean_requests, client, guest_index, index, index_name, user, reader, admin):
    # Check initial state: no requests, no role, no index
    assert await all_requests() == {}
    assert (await get_user_project_role(User(email=user), index)).role == Roles.NONE.name
    with pytest.raises(NotFoundError):
        await get_project_settings(index_name)
    # Create and retrieve requests for making index, assigning role

    await post_json(
        client,
        "/permission_requests",
        expected=204,
        user=user,
        json=dict(type="project_role", project_id=guest_index, role="ADMIN"),
    )
    await post_json(
        client,
        "/permission_requests",
        expected=204,
        user=user,
        json=dict(type="project_role", project_id=index, role="ADMIN"),
    )
    await post_json(
        client, "/permission_requests", expected=204, user=user, json=dict(type="create_project", project_id=index_name)
    )

    requests = [r.model_dump() | {"timestamp": r.timestamp and r.timestamp.isoformat()} async for r in list_all_requests()]

    # Let's reject the role request for index and approve the rest
    for r in requests:
        if r["request"]["project_id"] == index:
            r["status"] = "rejected"
        else:
            r["status"] = "approved"

    # Let's also create a request that we won't pass along
    await post_json(
        client,
        "/permission_requests",
        expected=204,
        user=reader,
        json=dict(type="project_role", project_id=index, role="ADMIN"),
    )
    # Let's go :D
    await post_json(client, "/permission_requests/admin", expected=204, user=admin, json=requests)
    # Now, the index should be made, the roles assigned, and the resolved requests disappeared
    assert (await get_user_project_role(User(email=user), guest_index)).role == Roles.ADMIN.name
    assert (await get_project_settings(index_name)).id == index_name
    assert (await get_user_project_role(User(email=user), index_name)).role == Roles.ADMIN.name
    # The rejected request should not be processed
    assert (await get_user_project_role(User(email=user), index)).role == Roles.NONE.name


@pytest.mark.anyio
async def test_api_post_admin_requests_auth(clean_requests, client, guest_index, index, index_name, user, reader):
    async def check_resolve(body, expected=204, **kargs):
        await check(
            await client.post("/permission_requests/admin", cookies=auth_cookie(user=reader), json=body),
            expected=expected,
            **kargs,
        )

    # You can only resolve a request for an index on which you are ADMIN
    await check_resolve(
        [dict(email=user, status="approved", request=dict(type="project_role", project_id=index, role="ADMIN"))], 403
    )
    await create_project_role(reader, index, Roles.ADMIN)
    await check_resolve([dict(email=user, request=dict(type="project_role", project_id=index, role="ADMIN"))])

    # You can only resolve a project creation request if you are server WRITER
    await check_resolve([dict(email=user, status="approved", request=dict(type="create_project", project_id=index_name))], 403)
    await update_server_role(reader, Roles.WRITER)
    await check_resolve([dict(email=user, status="approved", request=dict(type="create_project", project_id=index_name))])

    # If there are multiple requests you need permission for all of them
    await check_resolve(
        [
            dict(email=user, status="approved", request=dict(type="project_role", project_id=index, role="ADMIN")),
            dict(email=user, status="approved", request=dict(type="project_role", project_id=guest_index, role="ADMIN")),
        ],
        403,
    )
    # Server ADMIN is the boss
    await update_server_role(reader, Roles.ADMIN)
    await check_resolve(
        [
            dict(email=user, status="approved", request=dict(type="project_role", project_id=index, role="ADMIN")),
            dict(email=user, status="approved", request=dict(type="project_role", project_id=guest_index, role="ADMIN")),
        ]
    )
