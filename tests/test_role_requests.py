from elasticsearch import NotFoundError
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


def all_requests() -> dict[str, AdminPermissionRequest]:
    return {get_request_id(r): r for r in list_all_requests()}


def admin_requests(user: User) -> dict[str, AdminPermissionRequest]:
    return {get_request_id(r): r for r in list_admin_requests(user)}


def my_requests(user: User) -> dict[str, AdminPermissionRequest]:
    return {get_request_id(r): r for r in list_user_requests(user)}


def get_request_id(r: AdminPermissionRequest) -> str:
    ## unique requests are identified by (type, email, index)
    d = r.model_dump()
    return request_id(d["request"]["type"], d["email"], d["request"].get("project_id"))


def request_id(type: str, email: str, project_id: str | None = None) -> str:
    return f"{type}:{project_id or ''}:{email}"


def requests_ids(requests):
    return set([request_id(r["request"]["type"], r["email"], r["request"].get("project_id")) for r in requests])


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

    with pytest.raises(NotFoundError):
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
    request = dict(type="create_project", message="message", name="name", project_id=index_name)
    post_json(client, "/permission_requests", json=request, user=user, expected=204)
    r = get_json(client, "/permission_requests", user=user)
    assert len(r) == 1
    assert r[0]["request"]["message"] == "message"
    assert r[0]["request"]["name"] == "name"


def test_api_post_request(clean_requests, client, index, index_name, user):
    assert all_requests() == {}
    user_role_req = dict(type="project_role", project_id=index, role="ADMIN")
    user_proj_req = dict(type="create_project", project_id=index_name)
    user_role_id = request_id("project_role", user, index)
    user_proj_id = request_id("create_project", user, index_name)

    # Guests / unauthenticated users cannot post requests
    check(client.post("/permission_requests", json=user_role_req), expected=401)
    # Can we post role and project requests?
    post_json(
        client,
        "/permission_requests",
        expected=204,
        json=user_role_req,
        user=user,
    )
    assert set(all_requests().keys()) == {user_role_id}
    post_json(
        client,
        "/permission_requests",
        expected=204,
        json=user_proj_req,
        user=user,
    )
    assert set(all_requests().keys()) == {user_role_id, user_proj_id}


def test_api_get_my_requests(clean_requests, client, index, user):
    assert all_requests() == {}
    check(client.get("/permission_requests"), expected=401)
    assert get_json(client, "/permission_requests", user=user) == []
    post_json(
        client,
        "/permission_requests",
        user=user,
        json=dict(type="project_role", message="test", project_id=index, role="ADMIN"),
        expected=204,
    )
    (req,) = get_json(client, "/permission_requests", user=user)
    assert req["request"]["type"] == "project_role"
    assert req["request"]["role"] == "ADMIN"
    assert req["email"] == user
    post_json(
        client,
        "/permission_requests",
        user=user,
        json=dict(type="project_role", project_id=index, role="METAREADER"),
        expected=204,
    )
    (req,) = get_json(client, "/permission_requests", user=user)
    assert req["request"]["type"] == "project_role"
    assert req["request"]["role"] == "METAREADER"
    assert req["email"] == user


def test_api_get_admin_requests(clean_requests, client, guest_index, index, index_name, user, reader):
    assert all_requests() == {}
    project_req = dict(type="create_project", project_id=index_name)
    index_admin_req = dict(type="project_role", project_id=index, role="ADMIN")
    guest_admin_req = dict(type="project_role", project_id=guest_index, role="ADMIN")
    server_admin_req = dict(type="server_role", role="WRITER")
    project_req_id = request_id("create_project", user, index_name)
    index_admin_req_id = request_id("project_role", user, index)
    server_admin_req_id = request_id("server_role", user, None)

    post_json(client, "/permission_requests", expected=204, user=user, json=project_req)
    post_json(client, "/permission_requests", expected=204, user=user, json=index_admin_req)
    post_json(client, "/permission_requests", expected=204, user=user, json=guest_admin_req)
    post_json(client, "/permission_requests", expected=204, user=user, json=server_admin_req)

    # server READER (i.e. no server role) can see no requests
    assert get_json(client, "/permission_requests/admin", user=reader) == []
    # server WRITER can see project creation requests
    update_server_role(reader, Roles.WRITER)
    assert requests_ids(get_json(client, "/permission_requests/admin", user=reader)) == {project_req_id}
    # project WRITERS cannot see project role requests
    create_project_role(reader, index, Roles.WRITER)
    assert requests_ids(get_json(client, "/permission_requests/admin", user=reader)) == {project_req_id}
    # project ADMINs can see project role requests, but only for their own projects
    update_project_role(reader, index, Roles.ADMIN)
    assert requests_ids(get_json(client, "/permission_requests/admin", user=reader)) == {project_req_id, index_admin_req_id}
    # Server admins can see server role requests. They DO NOT see project role requests unless they are also project admins
    update_server_role(reader, Roles.ADMIN)
    assert requests_ids(get_json(client, "/permission_requests/admin", user=reader)) == {
        project_req_id,
        index_admin_req_id,
        server_admin_req_id,
    }


def test_api_post_admin_requests(clean_requests, client, guest_index, index, index_name, user, reader, admin):
    # Check initial state: no requests, no role, no index
    assert all_requests() == {}
    assert get_user_project_role(User(email=user), index).role == Roles.NONE.name
    with pytest.raises(NotFoundError):
        get_project_settings(index_name)
    # Create and retrieve requests for making index, assigning role

    post_json(
        client,
        "/permission_requests",
        expected=204,
        user=user,
        json=dict(type="project_role", project_id=guest_index, role="ADMIN"),
    )
    post_json(
        client, "/permission_requests", expected=204, user=user, json=dict(type="project_role", project_id=index, role="ADMIN")
    )
    post_json(client, "/permission_requests", expected=204, user=user, json=dict(type="create_project", project_id=index_name))
    requests = [
        r.model_dump() | {"timestamp": r.timestamp and r.timestamp.isoformat()} for r in list_admin_requests(User(email=admin))
    ]
    # Let's reject the role request for index
    for r in requests:
        if r["index"] == index:
            r["reject"] = True
    # Let's also create a request that we won't pass along
    post_json(
        client,
        "/permission_requests",
        expected=204,
        user=reader,
        json=dict(type="project_role", project_id=index, role="ADMIN"),
    )
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
        check(
            client.post("/permission_requests/admin", headers=build_headers(user=reader), json=body),
            expected=expected,
            **kargs,
        )

    check_resolve([])
    # You can only resolve a request for an index on which you are ADMIN
    check_resolve([dict(email=user, request=dict(type="project_role", project_id=index, role="ADMIN"))], 401)
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
