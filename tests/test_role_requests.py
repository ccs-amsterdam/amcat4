import pytest

from amcat4.index import IndexDoesNotExist, Role, get_index, get_role, set_global_role, set_role
from amcat4.requests import (
    CreateProjectRequest,
    PermissionRequest,
    RoleRequest,
    create_request,
    list_admin_requests,
    list_all_requests,
    list_user_requests,
    process_requests,
)
from tests.tools import build_headers, check, get_json, post_json


def all_requests() -> dict[tuple[str, str, str | None], PermissionRequest]:
    return {(r.request_type, r.email, r.index): r for r in list_all_requests()}


def keys(requests):
    print(requests)
    return {(r["request_type"], r["email"], r["index"]) for r in requests}


def test_role_requests(clean_requests, index, user):
    assert all_requests() == {}

    # Can we file a request?
    create_request(RoleRequest(index=index, email=user, role="ADMIN"))
    requests = all_requests()
    assert set(requests.keys()) == {("role", user, index)}
    r = requests["role", user, index]
    assert isinstance(r, RoleRequest)
    assert r.role == "ADMIN"
    assert r.timestamp is not None
    t = r.timestamp

    # Does re-filing the request update the timestamp
    create_request(RoleRequest(index=index, email=user, role="ADMIN"))
    requests = all_requests()
    assert set(requests.keys()) == {("role", user, index)}
    r = requests["role", user, index]
    assert isinstance(r, RoleRequest)
    assert r.role == "ADMIN"
    assert r.timestamp is not None
    assert r.timestamp > t

    # Updating a request
    create_request(RoleRequest(index=index, email=user, role="METAREADER"))
    requests = all_requests()

    assert set(requests.keys()) == {("role", user, index)}
    r = requests["role", user, index]
    assert isinstance(r, RoleRequest)
    assert r.role == "METAREADER"

    # Cancelling a request
    create_request(RoleRequest(index=index, email=user, role="NONE"))
    assert all_requests() == {}


def test_list_admin_requests(clean_requests, index, guest_index, index_name, user, admin):
    assert all_requests() == {}
    requests = {(r.request_type, r.email, r.index): r for r in list_admin_requests(user)}
    assert requests == {}
    create_request(RoleRequest(index=index, email="john@example.com", role="METAREADER"))
    create_request(RoleRequest(index=guest_index, email="jane@example.com", role="ADMIN"))
    create_request(CreateProjectRequest(index=index_name, email="john@example.com"))
    # An admin on a specific index should see requests for that index
    set_role(index, user, Role.ADMIN)
    requests = {(r.request_type, r.email, r.index): r for r in list_admin_requests(user)}
    assert set(requests.keys()) == {("role", "john@example.com", index)}
    set_role(guest_index, user, Role.ADMIN)
    requests = {(r.request_type, r.email, r.index): r for r in list_admin_requests(user)}
    assert set(requests.keys()) == {("role", "john@example.com", index), ("role", "jane@example.com", guest_index)}
    # A global writer can see project creation requests (???)
    set_global_role(user, Role.WRITER)
    set_role(guest_index, user, role=None)
    requests = {(r.request_type, r.email, r.index): r for r in list_admin_requests(user)}
    assert set(requests.keys()) == {("role", "john@example.com", index), ("create_project", "john@example.com", index_name)}
    # A global admin can see everything
    requests = {(r.request_type, r.email, r.index): r for r in list_admin_requests(admin)}
    assert set(requests.keys()) == {
        ("role", "john@example.com", index),
        ("role", "jane@example.com", guest_index),
        ("create_project", "john@example.com", index_name),
    }


def test_list_my_requests(clean_requests, index, index_name, user):
    assert list(list_user_requests(user)) == []
    create_request(RoleRequest(index=index, email="someoneelse@example.com", role="ADMIN"))
    assert list(list_user_requests(user)) == []
    create_request(RoleRequest(index=index, email=user, role="ADMIN"))
    requests = {(r.request_type, r.email, r.index): r for r in list_user_requests(user)}
    assert set(requests.keys()) == {("role", user, index)}
    assert requests[("role", user, index)].role == "ADMIN"
    create_request(CreateProjectRequest(index=index_name, email=user))
    requests = {(r.request_type, r.email, r.index): r for r in list_user_requests(user)}
    assert set(requests.keys()) == {("role", user, index), ("create_project", user, index_name)}


def test_resolve_requests(clean_requests, index, index_name, user, admin):
    assert all_requests() == {}
    assert get_role(index, user) == Role.NONE
    with pytest.raises(IndexDoesNotExist):
        get_index(index_name)
    create_request(RoleRequest(index=index, email=user, role="ADMIN"))
    create_request(CreateProjectRequest(index=index_name, email=user))
    requests = list(list_admin_requests(admin))
    assert len(requests) == 2
    process_requests(requests)
    assert get_role(index, user) == Role.ADMIN
    assert get_index(index_name).id == index_name
    assert get_role(index_name, user) == Role.ADMIN
    assert all_requests() == {}


def test_api_post_request(clean_requests, client, index, index_name, user):
    assert all_requests() == {}
    request = {"request_type": "role", "index": index, "email": user, "role": "ADMIN"}
    # Guests / unauthenticated users cannot post requests
    check(client.post("/permission_requests", json=request), expected=401)

    # Can we post role and project requests?
    post_json(
        client,
        "/permission_requests",
        expected=204,
        json=request,
        user=user,
    )
    assert set(all_requests().keys()) == {("role", user, index)}
    post_json(
        client,
        "/permission_requests",
        expected=204,
        json={"request_type": "create_project", "index": index_name, "email": user},
        user=user,
    )
    assert set(all_requests().keys()) == {("role", user, index), ("create_project", user, index_name)}


def test_api_get_my_requests(clean_requests, client, index, user):
    assert all_requests() == {}
    check(client.get("/permission_requests"), expected=401)
    assert get_json(client, "/permission_requests", user=user) == []
    create_request(RoleRequest(index=index, email="someoneelse@example.com", role="ADMIN"))
    assert get_json(client, "/permission_requests", user=user) == []
    create_request(RoleRequest(index=index, email=user, role="ADMIN"))
    (req,) = get_json(client, "/permission_requests", user=user)
    assert req["request_type"] == "role"
    assert req["email"] == user


def test_api_get_admin_requests(clean_requests, client, guest_index, index, index_name, user, reader):

    assert all_requests() == {}
    create_request(RoleRequest(index=index, email=user, role="ADMIN"))
    create_request(RoleRequest(index=guest_index, email=user, role="ADMIN"))
    create_request(CreateProjectRequest(index=index_name, email=user))

    # server WRITER can see no requests
    assert get_json(client, "/permission_requests/admin", user=reader) == []
    set_global_role(reader, Role.WRITER)
    assert keys(get_json(client, "/permission_requests/admin", user=reader)) == {("create_project", user, index_name)}
    set_role(index, reader, Role.ADMIN)
    assert keys(get_json(client, "/permission_requests/admin", user=reader)) == {
        ("create_project", user, index_name),
        ("role", user, index),
    }
    set_global_role(reader, Role.ADMIN)
    assert keys(get_json(client, "/permission_requests/admin", user=reader)) == {
        ("create_project", user, index_name),
        ("role", user, index),
        ("role", user, guest_index),
    }


def test_api_post_admin_requests(clean_requests, client, guest_index, index, index_name, user, admin):
    # Check initial state: no requests, no role, no index
    assert all_requests() == {}
    assert get_role(index, user) == Role.NONE
    with pytest.raises(IndexDoesNotExist):
        get_index(index_name)
    # Create and retrieve requests for making index, assigning role
    create_request(RoleRequest(index=index, email=user, role="ADMIN"))
    create_request(CreateProjectRequest(index=index_name, email=user))
    requests = [r.model_dump() | {"timestamp": r.timestamp and r.timestamp.isoformat()} for r in list_admin_requests(admin)]

    # Let's also create a request that we won't pass along
    create_request(RoleRequest(index=guest_index, email=user, role="ADMIN"))
    # Let's go :D
    post_json(client, "/permission_requests/admin", expected=204, user=admin, json=requests)
    # Now, the index should be made, the roles assigned, and the resolved requests disappeared
    assert get_role(index, user) == Role.ADMIN
    assert get_index(index_name).id == index_name
    assert get_role(index_name, user) == Role.ADMIN
    assert set(all_requests().keys()) == {("role", user, guest_index)}


def test_api_post_admin_requests_auth(clean_requests, client, guest_index, index, index_name, user, reader):
    def check_resolve(requests, expected=204, **kargs):
        body = [r.model_dump() | {"timestamp": r.timestamp and r.timestamp.isoformat()} for r in requests]
        check(
            client.post("/permission_requests/admin", headers=build_headers(user=reader), json=body),
            expected=expected,
            **kargs
        )

    check_resolve([])
    # You can only resolve a request for an index on which you are ADMIN
    check_resolve([RoleRequest(index=index, email=user, role="ADMIN")], 401)
    set_role(index, reader, Role.ADMIN)
    check_resolve([RoleRequest(index=index, email=user, role="ADMIN")])

    # You can only resolve a project creation request if you are server WRITER
    check_resolve([CreateProjectRequest(index=index_name, email=user)], 401)
    set_global_role(reader, Role.WRITER)
    check_resolve([CreateProjectRequest(index=index_name, email=user)])

    # If there are multiple requests you need permission for all of them
    check_resolve(
        [RoleRequest(index=index, email=user, role="ADMIN"), RoleRequest(index=guest_index, email=user, role="ADMIN")], 401
    )
    # Server ADMIN is the boss
    set_global_role(reader, Role.ADMIN)
    check_resolve(
        [RoleRequest(index=index, email=user, role="ADMIN"), RoleRequest(index=guest_index, email=user, role="ADMIN")]
    )
