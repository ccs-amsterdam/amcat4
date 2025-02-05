from datetime import datetime

from fastapi.testclient import TestClient

from amcat4.config import get_settings, AuthOptions
from tests.tools import get_json, create_token


def test_handler_responses(client: TestClient, admin):
    def test(expected=200, **payload):
        token = create_token(**payload)
        headers = {"Authorization": f"Bearer {token}"}
        return get_json(client, "/users/me", headers=headers, expected=expected)

    # Guests have no /me
    get_settings().auth = AuthOptions.no_auth
    assert client.get("/users/me").status_code == 404
    get_settings().auth = AuthOptions.allow_guests
    assert client.get("/users/me").status_code == 404
    # You need to login to access /users/me if auth is required
    get_settings().auth = AuthOptions.allow_authenticated_guests
    assert client.get("/users/me").status_code == 401
    get_settings().auth = AuthOptions.authorized_users_only
    assert client.get("/users/me").status_code == 401

    # A valid token needs a valid resource, expiry, and email
    now = int(datetime.now().timestamp())
    test(resource="http://localhost:3000", email=admin, expected=401)
    test(exp=now + 1000, email=admin, expected=401)
    assert test(resource="http://localhost:3000", exp=now + 1000, email=admin)["email"] == admin
    # Expired tokens don't work
    test(resource="http://localhost:3000", exp=now - 1000, email=admin, expected=401)
    # Wrong resource
    test(resource="http://wrong.com", exp=now + 1000, email=admin, expected=401)


def test_config(client: TestClient):
    result = get_json(client, "/config")
    assert result["middlecat_url"] == get_settings().middlecat_url
    assert result["authorization"] == get_settings().auth.name
