from datetime import datetime

import pytest
from httpx import AsyncClient

from amcat4.config import AuthOptions, get_settings
from amcat4.models import Roles
from tests.tools import create_token, get_json


@pytest.mark.anyio
async def test_handler_responses(client: AsyncClient, admin):
    async def test(expected=200, **payload):
        token = create_token(**payload)
        headers = {"Authorization": f"Bearer {token}"}
        return await get_json(client, "/users/me", headers=headers, expected=expected)

    # With no auth everyone is admin
    get_settings().auth = AuthOptions.no_auth
    me = (await client.get("/users/me")).json()
    assert me["role"] == Roles.ADMIN.name

    # With guest access, the role depends on the guest role (*),
    # which is NONE if not set
    get_settings().auth = AuthOptions.allow_guests
    me = (await client.get("/users/me")).json()
    assert me["role"] == Roles.NONE.name
    assert me["email"] == "*"

    # You need to login to access /users/me if auth is required
    get_settings().auth = AuthOptions.allow_authenticated_guests
    assert (await client.get("/users/me")).status_code == 401

    # A valid token needs a valid resource, expiry, and email
    now = int(datetime.now().timestamp())
    await test(resource="http://localhost:3000", email=admin, expected=401)
    await test(exp=now + 1000, email=admin, expected=401)
    assert (await test(resource="http://localhost:3000", exp=now + 1000, email=admin))["email"] == admin
    # Expired tokens don't work
    await test(resource="http://localhost:3000", exp=now - 1000, email=admin, expected=401)
    # Wrong resource
    await test(resource="http://wrong.com", exp=now + 1000, email=admin, expected=401)


@pytest.mark.anyio
async def test_config(client: AsyncClient):
    result = await get_json(client, "/config")
    assert result["middlecat_url"] == get_settings().middlecat_url
    assert result["authorization"] == get_settings().auth.name
