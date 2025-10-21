from fastapi.testclient import TestClient

from amcat4.config import AuthOptions
from amcat4.models import Roles, User
from amcat4.systemdata.roles import delete_server_role, get_user_server_role, set_project_guest_role
from tests.tools import get_json, build_headers, post_json, check, set_auth


def test_auth(client: TestClient, user, admin, index):
    unknown_user = "unknown@amcat.nl"
    with set_auth(AuthOptions.no_auth):
        # No auth - unauthenticated user can do anything
        assert client.get(f"/index/{index}").status_code == 200
        assert client.get(f"/index/{index}", headers=build_headers(admin)).status_code == 200
        assert client.get(f"/index/{index}", headers=build_headers(unknown_user)).status_code == 200
    with set_auth(AuthOptions.allow_guests):
        # Allow guests - unauthenticated user can access projects with guest roles
        assert client.get(f"/index/{index}").status_code == 403
        set_project_guest_role(index, Roles.READER)
        assert client.get(f"/index/{index}").status_code == 200
        assert client.get(f"/index/{index}", headers=build_headers(admin)).status_code == 200
    with set_auth(AuthOptions.allow_authenticated_guests):
        # Only use guest roles if user is authenticated
        assert client.get(f"/index/{index}").status_code == 401
        assert client.get(f"/index/{index}", headers=build_headers(unknown_user)).status_code == 200
        set_project_guest_role(index, Roles.NONE)
        assert client.get(f"/index/{index}", headers=build_headers(unknown_user)).status_code == 403
        assert client.get(f"/index/{index}", headers=build_headers(admin)).status_code == 200


def test_get_user(client: TestClient, writer, user):
    """Test GET user functionality and authorization"""
    # /users/me returns the assigned role (even for guests and if role is NONE)
    me = client.get("/users/me")
    assert me.status_code == 200
    assert me.json() == {"email": "*", "role": "NONE"}

    # user can only see its own info:
    assert get_json(client, "/users/me", user=user) == {"email": user, "role": "READER"}
    assert get_json(client, f"/users/{user}", user=user) == {"email": user, "role": "READER"}
    # writer can see everyone
    assert get_json(client, f"/users/{user}", user=writer) == {"email": user, "role": "READER"}
    assert get_json(client, f"/users/{writer}", user=writer) == {"email": writer, "role": "WRITER"}

    # Retrieving a non-existing user as admin gives the closest match (* if no domain match) with role NONE
    delete_server_role(user)
    assert get_json(client, f"/users/{user}", user=writer) == {"email": "*", "role": "NONE"}


def test_create_user(client: TestClient, user, writer, admin, username):
    # anonymous or unprivileged users cannot create new users
    new_user = dict(email=username, role="WRITER")
    assert client.post("/users/", json=new_user).status_code == 403, "Creating user should require auth"
    assert client.post("/users/", json=new_user, headers=build_headers(writer)).status_code == 403, (
        "Creating user should require admin"
    )
    # admin can add new users
    assert client.post("/users/", json=new_user, headers=build_headers(admin)).status_code == 201
    assert client.post("/users/", json=new_user, headers=build_headers(admin)).status_code == 409, (
        "Duplicate create should return 409"
    )

    # users can delete themselves, others cannot delete them
    assert client.delete(f"/users/{username}", headers=build_headers(writer)).status_code == 403
    assert client.delete(f"/users/{username}", headers=build_headers(username)).status_code == 204
    # (only) admin can delete everyone
    assert client.delete(f"/users/{user}", headers=build_headers(writer)).status_code == 403
    assert client.delete(f"/users/{user}", headers=build_headers(admin)).status_code == 204


def test_modify_user(client: TestClient, user, writer, admin):
    """Are the API endpoints and auth for modifying users correct?"""
    # Only admin can change users
    check(client.put(f"/users/{user}", headers=build_headers(user), json={"role": "WRITER"}), 403)
    check(client.put(f"/users/{user}", headers=build_headers(admin), json={"role": "ADMIN"}), 200)
    server_role = get_user_server_role(User(email=user))
    assert server_role and server_role.role == Roles.ADMIN.name


def test_list_users(client: TestClient, index, admin, user):
    # You need global WRITER rights to list users
    check(client.get("/users"), 403)
    check(client.get("/users", headers=build_headers(user)), 403)
    result = get_json(client, "/users", user=admin) or {}
    assert {"email": admin, "role": "ADMIN"} in result
    assert {"email": user, "role": "READER"} in result
