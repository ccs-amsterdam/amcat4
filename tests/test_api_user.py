from fastapi.testclient import TestClient

from amcat4.config import AuthOptions
from amcat4.index import delete_user, get_global_role, set_guest_role, Role
from tests.tools import get_json, build_headers, post_json, check, refresh, set_auth


def test_auth(client: TestClient, user, admin, index):
    unknown_user = "unknown@amcat.nl"
    with set_auth(AuthOptions.no_auth):
        # No auth - unauthenticated user can do anything
        assert client.get(f"/index/{index}").status_code == 200
        assert client.get(f"/index/{index}", headers=build_headers(admin)).status_code == 200
    with set_auth(AuthOptions.allow_guests):
        # Allow guests - unauthenticated user can access projects with guest roles
        assert client.get(f"/index/{index}").status_code == 401
        set_guest_role(index, Role.READER)
        refresh()
        assert client.get(f"/index/{index}").status_code == 200
        assert client.get(f"/index/{index}", headers=build_headers(admin)).status_code == 200
    with set_auth(AuthOptions.allow_authenticated_guests):
        # Only use guest roles if user is authenticated
        assert client.get(f"/index/{index}").status_code == 401
        assert client.get(f"/index/{index}", headers=build_headers(unknown_user)).status_code == 200
        set_guest_role(index, None)
        refresh()
        assert client.get(f"/index/{index}", headers=build_headers(unknown_user)).status_code == 401
        assert client.get(f"/index/{index}", headers=build_headers(admin)).status_code == 200
    with set_auth(AuthOptions.authorized_users_only):
        # Only users with a index-level role can access other indices (even as guest)
        set_guest_role(index, Role.READER)
        refresh()
        assert client.get(f"/index/{index}").status_code == 401
        assert client.get(f"/index/{index}", headers=build_headers(unknown_user)).status_code == 401
        assert client.get(f"/index/{index}", headers=build_headers(user)).status_code == 200


def test_get_user(client: TestClient, writer, user):
    """Test GET user functionality and authorization"""
    # Guests have no /me
    assert client.get("/users/me").status_code == 404
    # user can only see its own info:
    assert get_json(client, "/users/me", user=user) == {"email": user, "role": "READER"}
    assert get_json(client, f"/users/{user}", user=user) == {"email": user, "role": "READER"}
    # writer can see everyone
    assert get_json(client, f"/users/{user}", user=writer) == {"email": user, "role": "READER"}
    assert get_json(client, f"/users/{writer}", user=writer) == {"email": writer, "role": 'WRITER'}
    # Retrieving a non-existing user as admin should give 404
    delete_user(user)
    assert client.get(f'/users/{user}', headers=build_headers(writer)).status_code == 404


def test_create_user(client: TestClient, user, writer, admin, username):
    # anonymous or unprivileged users cannot create new users
    assert client.post('/users/').status_code == 401, "Creating user should require auth"
    assert client.post("/users/", headers=build_headers(writer)).status_code == 401, "Creating user should require admin"
    # admin can add new users
    u = dict(email=username, role="writer")
    assert "email" in set(post_json(client, "/users/", user=admin, json=u).keys())
    assert client.post("/users/", headers=build_headers(admin), json=u).status_code == 400, \
        "Duplicate create should return 400"

    # users can delete themselves, others cannot delete them
    assert client.delete(f"/users/{username}", headers=build_headers(writer)).status_code == 401
    assert client.delete(f"/users/{username}", headers=build_headers(username)).status_code == 204
    # (only) admin can delete everyone
    assert client.delete(f"/users/{user}", headers=build_headers(writer)).status_code == 401
    assert client.delete(f"/users/{user}", headers=build_headers(admin)).status_code == 204


def test_modify_user(client: TestClient, user, writer, admin):
    """Are the API endpoints and auth for modifying users correct?"""
    # Only admin can change users
    check(client.put(f"/users/{user}", headers=build_headers(user), json={'role': 'metareader'}), 401)
    check(client.put(f"/users/{user}", headers=build_headers(admin), json={'role': 'admin'}), 200)
    assert get_global_role(user).name == "ADMIN"


def test_list_users(client: TestClient, index, admin, user):
    # You need global WRITER rights to list users
    check(client.get("/users"), 401)
    check(client.get("/users", headers=build_headers(user)), 401)
    result = get_json(client, "/users", user=admin)
    assert {'email': admin, 'role': 'ADMIN'} in result
    assert {'email': user, 'role': 'READER'} in result
