import pytest
from httpx import AsyncClient

from amcat4.connections import es
from amcat4.models import Roles
from amcat4.systemdata.roles import (
    create_project_role,
    delete_project_role,
    get_project_guest_role,
    set_project_guest_role,
    update_project_role,
)
from tests.tools import auth_cookie, check, get_json, post_json, put_json


@pytest.mark.anyio
async def test_create_list_delete_index(client, index_name, user, writer, writer2, admin):
    """Test API endpoints to create/list/delete index"""
    new_index = dict(id=index_name, name=index_name)

    # Anonymous or Unprivileged users cannot create indices
    await check(await client.post("/index", json=new_index), 403)
    await check(await client.post("/index", json=new_index, cookies=auth_cookie(user=user)), 403)

    # Authorized users should get 404 if index does not exist
    await check(await client.get(f"/index/{index_name}"), 404)
    await check(await client.get(f"/index/{index_name}", cookies=auth_cookie(user=writer)), 404)

    # Writers can create indices
    await post_json(client, "/index", user=writer, json=new_index)
    assert index_name in {x["name"] for x in await get_json(client, "/index", user=writer) or []}

    # Users can GET their own index, admins can GET all indices, others cannot GET non-public indices
    await check(await client.get(f"/index/{index_name}"), 403)
    await check(await client.get(f"/index/{index_name}", cookies=auth_cookie(user=user)), 403)
    await check(await client.get(f"/index/{index_name}", cookies=auth_cookie(user=writer)), 200)
    await check(await client.get(f"/index/{index_name}", cookies=auth_cookie(user=writer2)), 403)
    await check(await client.get(f"/index/{index_name}", cookies=auth_cookie(user=admin)), 200)

    # Users can only see indices that they have a role in or that have a guest role
    assert index_name not in {x["name"] for x in await get_json(client, "/index", user=user) or []}
    assert index_name not in {x["name"] for x in await get_json(client, "/index", user=writer2) or []}
    assert index_name in {x["name"] for x in await get_json(client, "/index", user=writer) or []}

    # (Only) index admin can change index guest role
    await check(await client.put(f"/index/{index_name}", json={"guest_role": "METAREADER"}), 403)
    await check(
        await client.put(
            f"/index/{index_name}",
            cookies=auth_cookie(user=writer),
            json={"guest_role": "METAREADER"},
        ),
        204,
    )
    await check(
        await client.put(
            f"/index/{index_name}",
            cookies=auth_cookie(user=writer2),
            json={"guest_role": "READER"},
        ),
        403,
    )
    await check(
        await client.put(
            f"/index/{index_name}",
            cookies=auth_cookie(user=admin),
            json={"guest_role": "READER"},
        ),
        204,
    )
    assert await get_project_guest_role(index_name) == Roles.READER.name

    # Index should now be visible to non-authorized users
    assert index_name in {x["name"] for x in await get_json(client, "/index", user=writer) or []}
    await check(await client.get(f"/index/{index_name}", cookies=auth_cookie(user=user)), 200)


@pytest.mark.anyio
async def test_fields_upload(client: AsyncClient, user: str, index: str):
    """test_fields: Can we upload docs and retrieve field mappings and values?"""
    body = {
        "documents": [
            {
                "_id": str(i),
                "title": f"doc {i}",
                "text": "t",
                "date": "2021-01-01",
                "x": x,
            }
            for i, x in enumerate(["a", "a", "b"])
        ],
        "fields": {
            "title": "text",
            "text": "text",
            "date": "date",
            "x": "keyword",
        },
    }

    # You need METAREADER permissions to read fields, and WRITER to upload docs
    await check(await client.get(f"/index/{index}/fields"), 403)
    await check(
        await client.post(f"/index/{index}/documents", cookies=auth_cookie(user), json=body),
        403,
    )

    await create_project_role(user, index, Roles.METAREADER)

    # can get fields
    fields = await get_json(client, f"/index/{index}/fields", user=user) or {}
    # but should still be empty, since no fields were created
    assert len(set(fields.keys())) == 0
    await check(
        await client.post(f"/index/{index}/documents", cookies=auth_cookie(user), json=body),
        403,
    )

    await update_project_role(user, index, Roles.WRITER)
    await post_json(client, f"/index/{index}/documents", user=user, json=body)
    await get_json(client, f"/index/{index}/refresh", expected=204)
    doc = await get_json(client, f"/index/{index}/documents/0", user=user) or {}
    assert set(doc.keys()) == {"date", "text", "title", "x"}
    assert doc["title"] == "doc 0"

    # field selection
    assert set(
        (await get_json(client, f"/index/{index}/documents/0", user=user, params={"fields": "title"}) or {}).keys()
    ) == {"title"}
    assert (await get_json(client, f"/index/{index}/fields", user=user) or {})["x"]["type"] == "keyword"

    es_conn = es()
    await es_conn.indices.refresh()
    assert set(await get_json(client, f"/index/{index}/fields/x/values", user=user) or []) == {
        "a",
        "b",
    }


@pytest.mark.anyio
async def test_set_get_delete_roles(client: AsyncClient, admin: str, writer: str, user: str, index: str):
    body = {"email": user, "role": "READER"}
    # Anon, unauthorized, READER, WRITER can't create users
    await check(await client.post(f"/index/{index}/users", json=body), 403)
    await check(
        await client.post(f"/index/{index}/users", json=body, cookies=auth_cookie(writer)),
        403,
    )
    await create_project_role(user, index, Roles.READER)
    await check(
        await client.post(f"/index/{index}/users", json=body, cookies=auth_cookie(writer)),
        403,
    )
    await update_project_role(user, index, Roles.WRITER)
    await check(
        await client.post(f"/index/{index}/users", json=body, cookies=auth_cookie(writer)),
        403,
    )

    # Global admin can add or change users within an index
    # Add a WRITER role for writer
    await post_json(
        client,
        f"/index/{index}/users",
        json={"email": writer, "role": "WRITER"},
        user=admin,
    )
    # update the user to ADMIN
    await put_json(
        client,
        f"/index/{index}/users/{user}",
        json={"role": "ADMIN"},
        user=admin,
    )

    # Now there should be two users
    users = {u["email"]: u["role"] for u in await get_json(client, f"/index/{index}/users", user=user) or []}
    assert users == {user: "ADMIN", writer: "WRITER"}

    # user as ADMIN can now add a new user
    await post_json(client, f"/index/{index}/users", json={"email": "*@domain.com", "role": "READER"}, user=user)
    users = {u["email"]: u["role"] for u in await get_json(client, f"/index/{index}/users", user=user) or []}
    assert users == {user: "ADMIN", "*@domain.com": "READER", writer: "WRITER"}

    # Anon, unauthorized can't modify roles
    user_url = f"/index/{index}/users/{user}"
    writer_url = f"/index/{index}/users/{writer}"
    await check(await client.put(writer_url, json={"role": "READER"}), 403)
    await check(
        await client.put(writer_url, json={"role": "READER"}, cookies=auth_cookie(writer)),
        403,
    )
    # WRITER cant change, not even themselvs
    await check(
        await client.put(writer_url, json={"role": "READER"}, cookies=auth_cookie(writer)),
        403,
    )

    # ADMIN (user) can
    await check(
        await client.put(writer_url, json={"role": "READER"}, cookies=auth_cookie(user)),
        200,
    )
    users = {u["email"]: u["role"] for u in await get_json(client, f"/index/{index}/users", user=user) or []}
    assert users[writer] == "READER"

    # Anon can't delete
    await check(await client.delete(user_url), 403)
    # Writer can't delete
    await check(await client.delete(user_url, cookies=auth_cookie(writer)), 403)
    # Admin can delete
    await check(await client.delete(writer_url, cookies=auth_cookie(user)), 204)
    # Global admin can delete index admin
    await check(await client.delete(user_url, cookies=auth_cookie(admin)), 204)
    users = {u["email"]: u["role"] for u in await get_json(client, f"/index/{index}/users", user=admin) or []}
    assert user not in users


@pytest.mark.anyio
async def test_name_description(client, index, index_name, user, admin):
    # unauthenticated or unauthorized users cannot modify or view an index
    await check(await client.put(f"/index/{index}", json=dict(name="test")), 403)
    await check(await client.get(f"/index/{index}"), 403)
    await check(
        await client.put(f"/index/{index}", json=dict(name="test"), cookies=auth_cookie(user)),
        403,
    )
    await check(await client.get(f"/index/{index}", cookies=auth_cookie(user)), 403)

    # global admin and index writer can change details
    await check(
        await client.put(f"/index/{index}", json=dict(name="test"), cookies=auth_cookie(admin)),
        204,
    )

    await create_project_role(user, index, Roles.ADMIN)

    await check(
        await client.put(
            f"/index/{index}",
            json=dict(description="ooktest"),
            cookies=auth_cookie(user),
        ),
        204,
    )

    # global admin and index or guest metareader can read details
    assert (await get_json(client, f"/index/{index}", user=admin) or {})["description"] == "ooktest"
    assert (await get_json(client, f"/index/{index}", user=user) or {})["name"] == "test"
    await update_project_role(user, index, Roles.METAREADER)
    assert (await get_json(client, f"/index/{index}", user=user) or {})["name"] == "test"
    await delete_project_role(user, index)
    await check(await client.get(f"/index/{index}", cookies=auth_cookie(user)), 403)
    await set_project_guest_role(index, Roles.METAREADER)
    assert (await get_json(client, f"/index/{index}", user=user) or {})["name"] == "test"

    await check(
        await client.post(
            "/index",
            json=dict(
                id=index_name,
                description="test2",
                guest_role="METAREADER",
            ),
            cookies=auth_cookie(admin),
        ),
        201,
    )

    assert (await get_json(client, f"/index/{index_name}", user=user) or {})["description"] == "test2"

    indices = {ix["id"]: ix for ix in await get_json(client, "/index", user=user) or []}
    assert indices[index]["description"] == "ooktest"
    assert indices[index_name]["description"] == "test2"
