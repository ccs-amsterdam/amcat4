from starlette.testclient import TestClient

from amcat4.index import Role, get_role_requests, refresh_system_index, set_global_role, set_role, set_role_request
from tests.tools import build_headers, check, get_json, post_json


def test_role_requests(index):
    assert get_role_requests(index) == []
    set_role_request(index, "vanatteveldt@gmail.com", Role.ADMIN)
    refresh_system_index()
    requests = {r["email"]: r for r in get_role_requests(index)}
    assert len(requests) == 1
    result = requests["vanatteveldt@gmail.com"]
    assert result["role"] == "ADMIN"

    # Does re-filing the request update the timestamp
    set_role_request(index, "vanatteveldt@gmail.com", Role.ADMIN)
    refresh_system_index()
    requests = {r["email"]: r for r in get_role_requests(index)}
    assert len(requests) == 1
    assert requests["vanatteveldt@gmail.com"]["role"] == "ADMIN"
    assert requests["vanatteveldt@gmail.com"]["timestamp"] > result["timestamp"]

    # Updating a request
    set_role_request(index, "vanatteveldt@gmail.com", Role.METAREADER)
    refresh_system_index()
    requests = {r["email"]: r for r in get_role_requests(index)}
    assert len(requests) == 1
    assert requests["vanatteveldt@gmail.com"]["role"] == "METAREADER"

    # Cancelling a request
    set_role_request(index, "vanatteveldt@gmail.com", role=None)
    refresh_system_index()
    assert get_role_requests(index) == []


def test_role_request_api(client, index, user, admin):
    for url in [f"/index/{index}/role_requests", "/role_requests"]:
        post_json(client, url, user=user, json={"role": "ADMIN"}, expected=204)
        (r,) = get_json(client, url, user=admin)
        assert r["email"] == user
        assert r["role"] == "ADMIN"
        post_json(client, url, user=user, json={"role": "WRITER"}, expected=204)
        (r,) = get_json(client, url, user=admin)
        assert r["email"] == user
        assert r["role"] == "WRITER"
        post_json(client, url, user=user, json={"role": "NONE"}, expected=204)
        r = get_json(client, url, user=admin)
        assert len(r) == 0


def test_role_request_api_auth(client, index, user):
    # any authenticated user can post a role request
    check(client.post(f"/index/{index}/role_requests", json=dict(role="ADMIN")), 401)
    check(client.post(f"/index/{index}/role_requests", json=dict(role="ADMIN"), headers=build_headers(user=user)), 204)

    # only index admins can get role requests
    check(client.get(f"/index/{index}/role_requests"), 401)
    set_role(index, user, Role.WRITER)
    check(client.get(f"/index/{index}/role_requests", headers=build_headers(user=user)), 401)
    set_role(index, user, Role.ADMIN)
    check(client.get(f"/index/{index}/role_requests", headers=build_headers(user=user)), 200)


def test_server_role_request_api_auth(client, index, user):
    # any authenticated user can post a role request
    check(client.post(f"/role_requests", json=dict(role="ADMIN")), 401)
    check(client.post(f"/role_requests", json=dict(role="ADMIN"), headers=build_headers(user=user)), 204)

    # only index admins can get role requests
    check(client.get(f"/role_requests"), 401)
    set_global_role(user, Role.WRITER)
    check(client.get(f"/role_requests", headers=build_headers(user=user)), 401)
    set_global_role(user, Role.ADMIN)
    check(client.get(f"/role_requests", headers=build_headers(user=user)), 200)
