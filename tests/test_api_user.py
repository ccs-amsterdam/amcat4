from fastapi.testclient import TestClient

from amcat4.api.auth import verify_token
from amcat4.config import get_settings
from amcat4.index import delete_user, get_global_role
from tests.tools import get_json, build_headers, post_json, check


def test_admin_token(client: TestClient):
    get_settings().admin_password = "test"
    check(client.post('/auth/token'), 422, "Getting a token requires a form")
    check(client.post('/auth/token', data=dict(username="admin", password='wrong')), 401)
    r = client.post('/auth/token', data=dict(username="admin", password="test"))
    assert r.status_code == 200
    assert verify_token(r.json()['access_token'])['email'] == "admin"


def test_get_user(client: TestClient, writer, user):
    """Test GET user functionality and authorization"""
    assert client.get("/users/me").status_code == 401

    # user can only see its own info:
    assert get_json(client, "/users/me", user=user) == {"email": user, "global_role": "NONE"}
    assert get_json(client, f"/users/{user}", user=user) == {"email": user, "global_role": "NONE"}
    # writer can see everyone
    assert get_json(client, f"/users/{user}", user=writer) == {"email": user, "global_role": "NONE"}
    assert get_json(client, f"/users/{writer}", user=writer) == {"email": writer, "global_role": 'WRITER'}
    # Retrieving a non-existing user as admin should give 404
    delete_user(user)
    assert client.get(f'/users/{user}', headers=build_headers(writer)).status_code == 404


def test_create_user(client: TestClient, user, writer, admin, username):
    # anonymous or unprivileged users cannot create new users
    assert client.post('/users/').status_code == 401, "Creating user should require auth"
    assert client.post("/users/", headers=build_headers(writer)).status_code == 401, "Creating user should require admin"
    # admin can add new users
    u = dict(email=username, global_role="writer")
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
    check(client.put(f"/users/{user}", headers=build_headers(user), json={'global_role': 'metareader'}), 401)
    check(client.put(f"/users/{user}", headers=build_headers(admin), json={'global_role': 'admin'}), 200)
    assert get_global_role(user).name == "ADMIN"


def test_list_users(client: TestClient, index, admin, user):
    # You need global WRITER rights to list users
    check(client.get("/users"), 401)
    check(client.get("/users", headers=build_headers(user)), 401)
    result = get_json(client, "/users", user=admin)
    assert {'email': admin, 'global_role': 'ADMIN'} in result
    assert {'email': user, 'global_role': 'NONE'} in result
