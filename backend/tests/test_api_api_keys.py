import json

import pytest

from amcat4.models import Roles
from amcat4.systemdata.roles import create_project_role
from tests.tools import auth_cookie


@pytest.mark.anyio
async def test_create_api_key(client, index_name, admin):
    ## Create API key
    res = await client.post(
        "/api_keys",
        cookies=auth_cookie(admin),
        json={"name": "test_key", "expires_at": "2030-01-01T00:00:00Z"},
    )
    d = res.json()
    api_key_id = d["id"]
    api_key = d["api_key"]

    ## List API keys
    res = await client.get(
        "/api_keys",
        cookies=auth_cookie(user=admin),
    )
    assert res.json()[0]["name"] == "test_key"

    ## Use API key to create index
    res = await client.post(
        "/index",
        headers={"X-API-KEY": api_key},
        json={"id": index_name, "name": "Test Index"},
    )
    assert res.status_code == 201

    ## Use API key to check index
    res = await client.get(
        f"/index/{index_name}",
        headers={"X-API-KEY": api_key},
    )
    assert res.status_code == 200
    assert res.json()["id"] == index_name

    ## Default API keys should not be able to change their own settings
    res = await client.put(
        f"/api_keys/{api_key_id}",
        headers={"X-API-KEY": api_key},
        json={"expires_at": "2040-01-01T00:00:00Z"},
    )
    assert res.status_code == 403


@pytest.mark.anyio
async def test_api_key_expiration(client, index_name, admin):
    ## Create API key with expired date
    res = await client.post(
        "/api_keys",
        cookies=auth_cookie(user=admin),
        json={"name": "test_key", "expires_at": "2010-01-01T00:00:00Z"},
    )
    api_key = res.json()["api_key"]

    ## This key should be expired
    res = await client.post(
        "/index",
        headers={"X-API-KEY": api_key},
        json={"id": index_name, "name": "Test Index"},
    )
    assert res.status_code == 401
    assert "API key has expired" in res.text


@pytest.mark.anyio
async def test_api_key_restrictions(client, index, admin):
    await create_project_role(email=admin, project_id=index, role=Roles.ADMIN)

    ## Create API key with restricted access to the 'index' project
    res = await client.post(
        "/api_keys",
        cookies=auth_cookie(user=admin),
        json={
            "name": "test_key",
            "expires_at": "2030-01-01T00:00:00Z",
            "restrictions": {"server_role": "WRITER", "project_roles": {index: "READER"}},
        },
    )
    d = res.json()
    api_key_id = d["id"]
    api_key = d["api_key"]

    ## API key can not create users on the 'index' project, because restricted to READER role
    res = await client.post(
        f"/index/{index}/users",
        headers={"X-API-KEY": api_key},
        json={"email": "bob@gmail.com", "role": "READER"},
    )
    assert res.status_code == 403
    assert "does not have ADMIN permissions" in res.text

    ## Update API key to remove restrictions
    res = await client.put(
        f"/api_keys/{api_key_id}",
        cookies=auth_cookie(user=admin),
        json={
            "restrictions": {"project_roles": {}},
        },
    )

    ## Now API key can create users on the 'index' project
    res = await client.post(
        f"/index/{index}/users",
        headers={"X-API-KEY": api_key},
        json={"email": "bob@gmail.com", "role": "READER"},
    )
    assert res.status_code == 201

    ## Other restrictions besides project_roles are still in place
    res = await client.get(
        "/api_keys",
        cookies=auth_cookie(user=admin),
    )
    r = next(k for k in res.json() if k["id"] == api_key_id)
    assert r["restrictions"]["server_role"] == "WRITER"
