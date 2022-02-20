from amcat4.auth import verify_token, verify_user, Role, User
from tests.tools import get_json, build_headers, post_json


def test_get_token(client, user):
    assert client.get('/auth/token') == 401, "Getting a token should require authorization"
    r = get_json(client, '/auth/token', headers=build_headers(user=user.email, password=user.plaintext_password))
    assert verify_token(r['token']) == user


def test_get_user(client, user, admin, username):
    """Test GET user functionality and authorization"""
    assert client.get(f"/users/{user.email}") == 401

    # user can only see its own info:
    assert get_json(client, f"/users/{user.email}", user=user) == {"email": user.email, "global_role": None}
    assert client.get(f"/users/{admin.email}", headers=build_headers(user)) == 401
    # admin can see everyone
    assert get_json(client, f"/users/{user.email}", user=admin) == {"email": user.email, "global_role": None}
    assert get_json(client, f"/users/{admin.email}", user=admin) == {"email": admin.email, "global_role": 'ADMIN'}
    assert client.get(f'/users/{username}', headers=build_headers(admin)) == 404


def test_create_user(client, user, writer, admin, username):
    # anonymous or unprivileged users cannot create new users
    assert client.post('/users/') == 401, "Creating user should require auth"
    assert client.post("/users/", headers=build_headers(user)) == 401, "Creating user should require >=WRITER"
    # writers can add new users
    u = dict(email=username, password="geheim")
    assert set(post_json(client, "/users/", user=writer, json=u).keys()) == {"email", "id"}
    assert client.post("/users/", headers=build_headers(writer), json=u) == 400, "Duplicate create should return 400"
    # users can delete themselves, others cannot delete them
    assert client.delete(f"/users/{username}", headers=build_headers(user)) == 401
    assert client.delete(f"/users/{username}", headers=build_headers(username, password="geheim")) == 204
    # only admin can add admins
    u = dict(email=username, password="geheim", global_role='ADMIN')
    assert client.post("/users/", headers=build_headers(writer), json=u) == 401, "Creating admins should require ADMIN"
    assert client.post("/users/", headers=build_headers(admin), json=u) == 201
    assert get_json(client, f"/users/{username}", user=admin)["global_role"] == "ADMIN"
    # (only) admin can delete other admins
    assert client.delete(f"/users/{username}", headers=build_headers(writer)) == 401
    assert client.delete(f"/users/{username}", headers=build_headers(admin)) == 204


def test_modify_user(client, user, writer, admin):
    """Are the API endpoints and auth for modifying users correct?"""
    # Normal users can change their own password
    assert client.put(f"/users/{user.email}", headers=build_headers(user), json={'password': 'x'}) == 200
    assert verify_user(user.email, 'x') == user

    # Anonymous or normal users can't change other users
    assert client.put(f"/users/{user.email}") == 401, "Changing user requires AUTH"
    assert client.put(f"/users/{admin.email}", headers=build_headers(writer), json={'password': 'x'}) == 401

    # Writers can change other users, but not admins
    assert client.put(f"/users/{user.email}", headers=build_headers(writer), json={'password': 'y'}) == 200
    assert client.put(f"/users/{admin.email}", headers=build_headers(writer), json={'password': 'y'}) == 401

    # You can change privileges of other users up to your own privilege
    assert client.put(f"/users/{user.email}", headers=build_headers(user), json={'global_role': 'reader'}) == 401
    assert client.put(f"/users/{user.email}", headers=build_headers(writer), json={'global_role': 'writer'}) == 200
    assert User.get_by_id(user.id).global_role == Role.WRITER
    assert client.put(f"/users/{user.email}", headers=build_headers(writer), json={'global_role': 'admin'}) == 401
    assert client.put(f"/users/{writer.email}", headers=build_headers(admin), json={'global_role': 'admin'}) == 200
    assert User.get_by_id(writer.id).global_role == Role.ADMIN
