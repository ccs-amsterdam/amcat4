from datetime import datetime

import pytest
from httpx import AsyncClient

from amcat4.config import AuthOptions, get_settings
from amcat4.models import Roles
from tests.tools import create_session_cookie, create_token, get_json


@pytest.mark.anyio
async def test_handler_responses(client: AsyncClient, admin):
    async def test(expected=200, **payload):
        token = create_token(**payload)
        session_data = {"access_token": token}
        session_cookie = create_session_cookie(sessio_data)
        cookies = {"amcat_session": session_cookie}
        return await get_json(client, "/users/me", cookies=cookies, expected=expected)

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

    # A valid token needs a valid resource, clientId, expiry, and email
    now = int(datetime.now().timestamp())
    clientId = get_settings().host
    resource = get_settings().host + '/api'
    await test(clientId=clientId, resource=resource, email=admin, expected=401)
    await test(exp=now + 1000, email=admin, expected=401)
    assert (await test(clientId=clientId, resource=resource, exp=now + 1000, email=admin))["email"] == admin
    # Expired tokens don't work
    await test(clientId=clientId, resource=resource, exp=now - 1000, email=admin, expected=401)
    # Wrong resource
    await test(clientId=clientId, resource="http://nee.niet", exp=now + 1000, email=admin, expected=401)


@pytest.mark.anyio
async def test_config(client: AsyncClient):
    result = await get_json(client, "/config")

    assert result["middlecat_url"] == get_settings().middlecat_url
    assert result["authorization"] == get_settings().auth.name
