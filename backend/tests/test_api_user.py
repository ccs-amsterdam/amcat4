import pytest
from httpx import AsyncClient

from amcat4.config import AuthOptions
from amcat4.models import Roles, User
from amcat4.systemdata.roles import delete_server_role, get_user_server_role, set_project_guest_role
from tests.tools import auth_cookie, check, get_json, set_auth


@pytest.mark.anyio
async def test_auth(client: AsyncClient, admin, index):
    unknown_user = "unknown@amcat.nl"
    with set_auth(AuthOptions.no_auth):
        # No auth - unauthenticated user can do anything
        assert (await client.get(f"/index/{index}")).status_code == 200
        assert (await client.get(f"/index/{index}", cookies=auth_cookie(admin))).status_code == 200
        assert (await client.get(f"/index/{index}", cookies=auth_cookie(unknown_user))).status_code == 200
    with set_auth(AuthOptions.allow_guests):
        # Allow guests - unauthenticated user can access projects with guest roles
        assert (await client.get(f"/index/{index}")).status_code == 403
        await set_project_guest_role(index, Roles.READER)
        assert (await client.get(f"/index/{index}")).status_code == 200
        assert (await client.get(f"/index/{index}", cookies=auth_cookie(admin))).status_code == 200
    with set_auth(AuthOptions.allow_authenticated_guests):
        # Only use guest roles if user is authenticated
        assert (await client.get(f"/index/{index}")).status_code == 401
        assert (await client.get(f"/index/{index}", cookies=auth_cookie(unknown_user))).status_code == 200
        await set_project_guest_role(index, Roles.NONE)
        assert (await client.get(f"/index/{index}", cookies=auth_cookie(unknown_user))).status_code == 403
        assert (await client.get(f"/index/{index}", cookies=auth_cookie(admin))).status_code == 200


@pytest.mark.anyio
async def test_get_user(client: AsyncClient, writer, user):
    """Test GET user functionality and authorization"""
    # /users/me returns the assigned role (even for guests and if role is NONE)
    me = await client.get("/users/me")
    assert me.status_code == 200
    assert me.json() == {"email": "*", "role": "NONE"}

    # user can only see its own info:
    assert await get_json(client, "/users/me", user=user) == {"email": user, "role": "READER"}
    assert await get_json(client, f"/users/{user}", user=user) == {"email": user, "role": "READER"}
    # writer can see everyone
    assert await get_json(client, f"/users/{user}", user=writer) == {"email": user, "role": "READER"}
    assert await get_json(client, f"/users/{writer}", user=writer) == {"email": writer, "role": "WRITER"}

    # Retrieving a non-existing user as admin gives the closest match (* if no domain match) with role NONE
    await delete_server_role(user)
    assert await get_json(client, f"/users/{user}", user=writer) == {"email": "*", "role": "NONE"}


@pytest.mark.anyio
async def test_create_user(client: AsyncClient, user, writer, admin, username):
    # anonymous or unprivileged users cannot create new users
    new_user = dict(email=username, role="WRITER")
    assert (await client.post("/users", json=new_user)).status_code == 403, "Creating user should require auth"
    assert (await client.post("/users", json=new_user, cookies=auth_cookie(writer))).status_code == 403, (
        "Creating user should require admin"
    )
    # admin can add new users
    assert (await client.post("/users", json=new_user, cookies=auth_cookie(admin))).status_code == 201
    assert (await client.post("/users", json=new_user, cookies=auth_cookie(admin))).status_code == 409, (
        "Duplicate create should return 409"
    )

    # users can delete themselves, others cannot delete them
    assert (await client.delete(f"/users/{username}", cookies=auth_cookie(writer))).status_code == 403
    assert (await client.delete(f"/users/{username}", cookies=auth_cookie(username))).status_code == 204
    # (only) admin can delete everyone
    assert (await client.delete(f"/users/{user}", cookies=auth_cookie(writer))).status_code == 403
    assert (await client.delete(f"/users/{user}", cookies=auth_cookie(admin))).status_code == 204


@pytest.mark.anyio
async def test_modify_user(client: AsyncClient, user, writer, admin):
    """Are the API endpoints and auth for modifying users correct?"""
    # Only admin can change users
    await check(await client.put(f"/users/{user}", cookies=auth_cookie(user), json={"role": "WRITER"}), 403)
    await check(await client.put(f"/users/{user}", cookies=auth_cookie(admin), json={"role": "ADMIN"}), 200)
    server_role = await get_user_server_role(User(email=user))
    assert server_role and server_role.role == Roles.ADMIN.name


@pytest.mark.anyio
async def test_list_users(client: AsyncClient, index, admin, user):
    # You need global WRITER rights to list users
    await check(await client.get("/users"), 403)
    await check(await client.get("/users", cookies=auth_cookie(user)), 403)
    result = await get_json(client, "/users", user=admin) or {}
    assert {"email": admin, "role": "ADMIN"} in result
    assert {"email": user, "role": "READER"} in result
