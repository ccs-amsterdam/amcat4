from fastapi import HTTPException
import pytest

from amcat4.models import AdminPermissionRequest, ProjectRoleRequest, Roles, User
from amcat4.projects.index import IndexDoesNotExist
from amcat4.systemdata.requests import (
    delete_request,
    update_request,
    list_admin_requests,
    list_all_requests,
    list_user_requests,
    process_request,
)
from amcat4.models import CreateProjectRequest
from amcat4.systemdata.roles import (
    create_project_role,
    delete_project_role,
    get_user_project_role,
    update_project_role,
    update_server_role,
)
from amcat4.systemdata.settings import get_project_settings
from tests.tools import build_headers, check, get_json, post_json


def all_requests() -> dict[tuple[str, str, str | None], AdminPermissionRequest]:
    return {get_request_id(r): r for r in list_all_requests()}


def admin_requests(user: User) -> dict[tuple[str, str, str | None], AdminPermissionRequest]:
    return {get_request_id(r): r for r in list_admin_requests(user)}


def my_requests(user: User) -> dict[tuple[str, str, str | None], AdminPermissionRequest]:
    return {get_request_id(r): r for r in list_user_requests(user)}


def get_request_id(r: AdminPermissionRequest) -> str:
    ## unique requests are identified by (type, email, index)
    return request_id(r.request.type, r.email, r.request.project_id)


def request_id(type: str, email: str, project_id: str | None = None) -> str:
    return f"{type}:{project_id or ''}:{email}"


def keys(requests):
    return {(r["type"], r["email"], r["index"]) for r in requests}


def test_role_requests(clean_requests, index, user):
    assert all_requests() == {}

    # Can we file a request?
    update_request(
        AdminPermissionRequest(email=user, request=ProjectRoleRequest(type="project_role", project_id=index, role="ADMIN"))
    )

    requests = all_requests()
    id = request_id("project_role", user, index)
    assert set(requests.keys()) == {id}
    r = requests[id]
    assert isinstance(r, AdminPermissionRequest)
    assert r.request.role == "ADMIN"
    assert r.timestamp is not None
    t = r.timestamp

    # Does re-filing the request update the timestamp
    update_request(
        AdminPermissionRequest(email=user, request=ProjectRoleRequest(type="project_role", project_id=index, role="ADMIN"))
    )
    requests = all_requests()
    assert set(requests.keys()) == {id}
    r = requests[id]
    assert isinstance(r, AdminPermissionRequest)
    assert r.request.role == "ADMIN"
    assert r.timestamp is not None
    assert r.timestamp > t

    # Updating a request
    update_request(
        AdminPermissionRequest(
            email=user, request=ProjectRoleRequest(type="project_role", project_id=index, role="METAREADER")
        )
    )
    requests = all_requests()

    assert set(requests.keys()) == {id}
    r = requests[id]
    assert isinstance(r, AdminPermissionRequest)
    assert r.request.role == "METAREADER"

    # Cancelling a request
    delete_request(
        AdminPermissionRequest(
            email=user, request=ProjectRoleRequest(type="project_role", project_id=index, role="METAREADER")
        )
    )
    assert all_requests() == {}


def test_list_admin_requests(clean_requests, index, guest_index, index_name, user, admin):
    user_obj = User(email=user)

    assert all_requests() == {}
    requests = admin_requests(user_obj)
    assert requests == {}

    ## Make three requests
    update_request(
        AdminPermissionRequest(
            email="john@example.com", request=ProjectRoleRequest(type="project_role", project_id=index, role="METAREADER")
        )
    )
    update_request(
        AdminPermissionRequest(
            email="jane@example.com", request=ProjectRoleRequest(type="project_role", project_id=guest_index, role="ADMIN")
        )
    )
    update_request(
        AdminPermissionRequest(
            email="john@example.com", request=CreateProjectRequest(type="create_project", project_id=index_name)
        )
    )
    ## create their ids (for ease of testing assertions)
    john_role_req = request_id("project_role", "john@example.com", index)
    jane_role_req = request_id("project_role", "jane@example.com", guest_index)
    john_create_req = request_id("create_project", "john@example.com", index_name)

    update_request(
        AdminPermissionRequest(
            email="john@example.com", request=CreateProjectRequest(type="create_project", project_id=index_name)
        )
    )

    # An admin on a specific index should see requests for that index
    create_project_role(user, index, Roles.ADMIN)

    requests = admin_requests(user_obj)
    assert set(requests.keys()) == {john_role_req}

    create_project_role(user, guest_index, Roles.ADMIN)
    requests = admin_requests(user_obj)
    assert set(requests.keys()) == {john_role_req, jane_role_req}

    # A global writer can see project creation requests (???)
    update_server_role(user, Roles.WRITER)
    delete_project_role(user, guest_index)
    requests = admin_requests(user_obj)
    assert set(requests.keys()) == {john_role_req, john_create_req}

    admin_obj = User(email=admin)
    requests = admin_requests(admin_obj)

    assert set(requests.keys()) == {john_create_req}


def test_list_my_requests(clean_requests, index, index_name, user):
    user_obj = User(email=user)

    assert list(list_user_requests(user_obj)) == []
    update_request(
        AdminPermissionRequest(
            email="someoneelse@example.com", request=ProjectRoleRequest(type="project_role", project_id=index, role="ADMIN")
        )
    )
    assert list(list_user_requests(user_obj)) == []
    update_request(
        AdminPermissionRequest(email=user, request=ProjectRoleRequest(type="project_role", project_id=index, role="ADMIN"))
    )
    user_role_req = request_id("project_role", user, index)

    requests = my_requests(user_obj)
    assert set(requests.keys()) == {user_role_req}

    role_request = requests[user_role_req]
    assert role_request.request.type == "project_role"
    assert role_request.request.role == Roles.ADMIN.name

    update_request(
        AdminPermissionRequest(email=user, request=CreateProjectRequest(type="create_project", project_id=index_name))
    )
    user_create_req = request_id("create_project", user, index_name)
    requests = my_requests(user_obj)

    assert set(requests.keys()) == {user_role_req, user_create_req}


def test_resolve_requests(clean_requests, index, index_name, user, admin):
    user_obj = User(email=user)
    admin_obj = User(email=admin)

    assert all_requests() == {}
    assert get_user_project_role(user_obj, index).role == Roles.NONE.name

    with pytest.raises(HTTPException):
        get_project_settings(index_name)

    update_project_role(admin, index, Roles.ADMIN, ignore_missing=True)
    update_request(
        AdminPermissionRequest(email=user, request=ProjectRoleRequest(type="project_role", project_id=index, role="ADMIN"))
    )
    update_request(
        AdminPermissionRequest(email=user, request=CreateProjectRequest(type="create_project", project_id=index_name))
    )

    requests = list(list_admin_requests(admin_obj))
    ## created 2 requests
    assert len(requests) == 2

    ## Update status and process request
    for request in requests:
        request.status = "approved"
        process_request(request)

    assert get_user_project_role(user_obj, index).role == Roles.ADMIN.name
    assert get_project_settings(index_name).id == index_name

    ## Admins can no longer see the processed requests
    assert len(list(list_admin_requests(admin_obj))) == 0

    ## User that submitted them can see the updated status.
    ## Users can also delete requests (or cancel them by deleting before being processed)
    for request in list_user_requests(user_obj):
        assert request.status == "approved"
        delete_request(request)

    # Now all requests are gone
    assert len(list(list_all_requests())) == 0


def test_project_attributes(clean_requests, index_name, user, admin):
    admin_obj = User(email=admin)
    update_request(
        AdminPermissionRequest(
            email=user,
            message="message",
            request=CreateProjectRequest(project_id=index_name, name="name", type="create_project"),
        )
    )

    requests = list(list_admin_requests(admin_obj))
    for request in requests:
        request.status = "approved"
        process_request(request)

    assert get_project_settings(index_name).name == "name"


def test_request_attributes_api(clean_requests, client, index_name, user):
    request = dict(email=user, message="message", request=dict(type="create_project", name="name", project_id=index_name))
    post_json(client, "/permission_requests", json=request, user=user, expected=204)
    r = get_json(client, "/permission_requests", user=user)
    assert len(r) == 1
    assert r[0]["message"] == "message"
    assert r[0]["request"]["name"] == "name"


def test_api_post_request(clean_requests, client, index, index_name, user):
    assert all_requests() == {}
    request = dict(type="role", role_context=index, email=user, role="ADMIN")
    # Guests / unauthenticated users cannot post requests
    check(client.post("/permission_requests", json=request), expected=401)
    # You cannot post a request for someone else
    check(
        client.post("/permission_requests", json=request | {"email": "me@me.com"}, headers=build_headers(user=user)),
        expected=401,
    )
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
        json={"type": "create_project", "index": index_name, "email": user},
        user=user,
    )
    assert set(all_requests().keys()) == {("role", user, index), ("create_project", user, index_name)}


def test_api_get_my_requests(clean_requests, client, index, user):
    assert all_requests() == {}
    check(client.get("/permission_requests"), expected=401)
    assert get_json(client, "/permission_requests", user=user) == []
    update_request(RoleRequest(role_context=index, email="someoneelse@example.com", role="ADMIN"))
    assert get_json(client, "/permission_requests", user=user) == []
    update_request(RoleRequest(role_context=index, email=user, role="ADMIN"))
    (req,) = get_json(client, "/permission_requests", user=user)
    assert req["type"] == "role"
    assert req["email"] == user


def test_api_get_admin_requests(clean_requests, client, guest_index, index, index_name, user, reader):
    assert all_requests() == {}
    update_request(RoleRequest(role_context=index, email=user, role="ADMIN"))
    update_request(RoleRequest(role_context=guest_index, email=user, role="ADMIN"))
    update_request(CreateProjectRequest(role_context=index_name, email=user))

    # server WRITER can see no requests
    assert get_json(client, "/permission_requests/admin", user=reader) == []
    update_server_role(reader, Roles.WRITER)
    assert keys(get_json(client, "/permission_requests/admin", user=reader)) == {("create_project", user, index_name)}
    update_project_role(reader, index, Roles.WRITER)
    assert keys(get_json(client, "/permission_requests/admin", user=reader)) == {
        ("create_project", user, index_name),
        ("role", user, index),
    }
    update_server_role(reader, Roles.ADMIN)
    assert keys(get_json(client, "/permission_requests/admin", user=reader)) == {
        ("create_project", user, index_name),
        ("role", user, index),
        ("role", user, guest_index),
    }


def test_api_post_admin_requests(clean_requests, client, guest_index, index, index_name, user, reader, admin):
    # Check initial state: no requests, no role, no index
    assert all_requests() == {}
    assert get_user_project_role(User(email=user), index).role == Roles.NONE
    with pytest.raises(IndexDoesNotExist):
        get_project_settings(index_name)
    # Create and retrieve requests for making index, assigning role
    update_request(RoleRequest(role_context=guest_index, email=user, role="ADMIN"))
    update_request(RoleRequest(role_context=index, email=user, role="ADMIN"))
    update_request(CreateProjectRequest(role_context=index_name, email=user))
    requests = [r.model_dump() | {"timestamp": r.timestamp and r.timestamp.isoformat()} for r in list_admin_requests(admin)]
    # Let's reject the role request for index
    for r in requests:
        if r["index"] == index:
            r["reject"] = True
    # Let's also create a request that we won't pass along
    update_request(RoleRequest(role_context=index, email=reader, role="ADMIN"))
    # Let's go :D
    post_json(client, "/permission_requests/admin", expected=204, user=admin, json=requests)
    # Now, the index should be made, the roles assigned, and the resolved requests disappeared
    assert get_user_project_role(User(email=user), guest_index).role == Roles.ADMIN.name
    assert get_project_settings(index_name).id == index_name
    assert get_user_project_role(User(email=user), index_name).role == Roles.ADMIN.name
    # The rejected request should not be processed
    assert get_user_project_role(User(email=user), index).role == Roles.NONE.name
    # But it should be cleared, and the only request left should be the one from 'reader'
    assert set(all_requests().keys()) == {("role", reader, index)}


def test_api_post_admin_requests_auth(clean_requests, client, guest_index, index, index_name, user, reader):
    def check_resolve(requests, expected=204, **kargs):
        body = [r.model_dump() | {"timestamp": r.timestamp and r.timestamp.isoformat()} for r in requests]
        check(
            client.post("/permission_requests/admin", headers=build_headers(user=reader), json=body),
            expected=expected,
            **kargs,
        )

    check_resolve([])
    # You can only resolve a request for an index on which you are ADMIN
    check_resolve([RoleRequest(role_context=index, email=user, role="ADMIN")], 401)
    update_project_role(reader, index, Roles.ADMIN)
    check_resolve([RoleRequest(role_context=index, email=user, role="ADMIN")])

    # You can only resolve a project creation request if you are server WRITER
    check_resolve([CreateProjectRequest(role_context=index_name, email=user)], 401)
    update_server_role(reader, Roles.WRITER)
    check_resolve([CreateProjectRequest(role_context=index_name, email=user)])

    # If there are multiple requests you need permission for all of them
    check_resolve(
        [
            RoleRequest(role_context=index, email=user, role="ADMIN"),
            RoleRequest(role_context=guest_index, email=user, role="ADMIN"),
        ],
        401,
    )
    # Server ADMIN is the boss
    update_server_role(reader, Roles.ADMIN)
    check_resolve(
        [
            RoleRequest(role_context=index, email=user, role="ADMIN"),
            RoleRequest(role_context=guest_index, email=user, role="ADMIN"),
        ]
    )
