import pytest

from amcat4.models import CreateDocumentField, FieldSpec, Roles
from amcat4.projects.index import refresh_index
from amcat4.projects.query import query_documents
from amcat4.systemdata.roles import create_project_role, update_project_role
from tests.conftest import upload
from tests.tools import auth_cookie, check, dictset, post_json


@pytest.mark.anyio
async def test_query_post(client, index_docs, user):
    await create_project_role(user, index_docs, Roles.READER)

    async def q(**body):
        res = await post_json(client, f"/index/{index_docs}/query", user=user, expected=200, json=body)
        return res["results"]

    async def qi(**query_string):
        return {int(doc["_id"]) for doc in await q(**query_string)}

    # Query strings
    assert await qi(queries="text") == {0, 1}
    assert await qi(queries="test*") == {1, 2, 3}
    assert await qi(queries={}) == {0, 1, 2, 3}
    assert await qi(queries={"test": "test*"}) == {1, 2, 3}

    # Filters
    assert await qi(filters={"cat": "a"}) == {0, 1, 2}
    assert await qi(filters={"cat": "b"}, queries="test*") == {3}
    assert await qi(filters={"date": "2018-01-01"}) == {0, 3}
    assert await qi(filters={"date": {"gte": "2018-02-01"}}) == {1, 2}
    assert await qi(filters={"date": {"gt": "2018-02-01"}}) == {2}
    assert await qi(filters={"date": {"gte": "2018-02-01", "lt": "2020-01-01"}}) == {1}
    assert await qi(filters={"cat": {"values": ["a"]}}) == {0, 1, 2}

    # Can we request specific fields?
    all_fields = {"_id", "cat", "subcat", "i", "date", "text", "title"}
    assert set((await q())[0].keys()) == all_fields
    assert set((await q(fields=["cat"]))[0].keys()) == {"_id", "cat"}
    assert set((await q(fields=["date", "title"]))[0].keys()) == {"_id", "date", "title"}


@pytest.mark.anyio
async def test_aggregate(client, index_docs, user):
    await create_project_role(user, index_docs, Roles.READER)
    r = await post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={"axes": [{"field": "cat"}]},
    )
    assert r["meta"]["axes"][0]["field"] == "cat"
    data = {d["cat"]: d["n"] for d in r["data"]}
    assert data == {"a": 3, "b": 1}

    # test calculated field
    r = await post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={
            "axes": [{"field": "subcat"}],
            "aggregations": [{"field": "i", "function": "avg"}],
        },
    )
    assert dictset(r["data"]) == dictset([{"avg_i": 1.5, "n": 2, "subcat": "x"}, {"avg_i": 21.0, "n": 2, "subcat": "y"}])
    assert r["meta"]["aggregations"] == [{"field": "i", "function": "avg", "type": "integer", "name": "avg_i"}]

    # test filtered aggregate
    r = await post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={"axes": [{"field": "subcat"}], "filters": {"cat": {"values": ["b"]}}},
    )
    data = {d["subcat"]: d["n"] for d in r["data"]}
    assert data == {"y": 1}

    # test filter+query aggregate
    r = await post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={
            "axes": [{"field": "subcat"}],
            "queries": "text",
            "filters": {"cat": {"values": ["a"]}},
        },
    )
    data = {d["subcat"]: d["n"] for d in r["data"]}
    assert data == {"x": 2}


@pytest.mark.anyio
async def test_bare_aggregate(client, index_docs, user):
    await create_project_role(user, index_docs, Roles.READER)
    r = await post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={},
    )
    assert r["meta"]["axes"] == []
    assert r["data"] == [dict(n=4)]

    r = await post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={"aggregations": [{"field": "i", "function": "avg"}]},
    )
    assert r["data"] == [dict(n=4, avg_i=11.25)]

    r = await post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={"aggregations": [{"field": "i", "function": "min", "name": "mini"}]},
    )
    assert r["data"] == [dict(n=4, mini=1)]


@pytest.mark.anyio
async def test_multiple_index(client, index_docs, index, user):
    await create_project_role(user, index_docs, Roles.READER)
    await create_project_role(user, index, Roles.READER)

    await upload(
        index,
        [{"text": "also a text", "i": -1, "cat": "c"}],
        fields={
            "text": CreateDocumentField(type="text"),
            "cat": CreateDocumentField(type="keyword"),
            "i": CreateDocumentField(type="integer"),
        },
    )
    indices = f"{index},{index_docs}"

    r = await post_json(
        client,
        f"/index/{indices}/query",
        user=user,
        expected=200,
        json=dict(fields=["_id", "cat", "i"]),
    )
    assert len(r["results"]) == 5

    r = await post_json(
        client,
        f"/index/{indices}/aggregate",
        user=user,
        json={"axes": [{"field": "cat"}], "fields": ["_id"]},
        expected=200,
    )
    assert dictset(r["data"]) == dictset([{"cat": "a", "n": 3}, {"n": 1, "cat": "b"}, {"n": 1, "cat": "c"}])


@pytest.mark.anyio
async def test_aggregate_datemappings(client, index_docs, user):
    await create_project_role(user, index_docs, Roles.READER)

    r = await post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={"axes": [{"field": "date", "interval": "monthnr"}]},
    )
    assert r["data"] == [{"date_monthnr": 1, "n": 3}, {"date_monthnr": 2, "n": 1}]
    assert [x["name"] for x in r["meta"]["axes"]] == ["date_monthnr"]
    r = await post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={
            "axes": [
                {"field": "date", "interval": "monthnr"},
                {"field": "date", "interval": "dayofmonth"},
            ]
        },
    )
    assert [x["name"] for x in r["meta"]["axes"]] == ["date_monthnr", "date_dayofmonth"]
    assert r["data"] == [
        {"date_monthnr": 1, "date_dayofmonth": 1, "n": 3},
        {"date_monthnr": 2, "date_dayofmonth": 1, "n": 1},
    ]


@pytest.mark.anyio
async def test_query_tags(client, index_docs, user):
    await create_project_role(user, index_docs, Roles.READER)

    async def tags():
        result = await query_documents(index_docs, fields=[FieldSpec(name="tag")])
        return {doc["_id"]: doc["tag"] for doc in (result.data if result else []) if doc.get("tag")}

    add_tags = dict(action="add", field="tag", tag="x", filters={"cat": "a"})

    await check(await client.post(f"/index/{index_docs}/tags_update", json=add_tags), 403)
    await check(await client.post(f"/index/{index_docs}/tags_update", json=add_tags, cookies=auth_cookie(user=user)), 403)

    await update_project_role(user, index_docs, Roles.WRITER)

    assert await tags() == {}
    res = await post_json(client, f"/index/{index_docs}/tags_update", user=user, expected=200, json=add_tags)
    assert res["updated"] == 3
    # should refresh before returning
    # await refresh_index(index_docs)
    assert await tags() == {"0": ["x"], "1": ["x"], "2": ["x"]}
    res = await post_json(
        client,
        f"/index/{index_docs}/tags_update",
        user=user,
        expected=200,
        json=dict(action="remove", field="tag", tag="x", queries=["text"]),
    )
    assert res["updated"] == 2
    assert await tags() == {"2": ["x"]}
    res = await post_json(
        client,
        f"/index/{index_docs}/tags_update",
        user=user,
        expected=200,
        json=dict(action="add", field="tag", tag="y", ids=["1", "2"]),
    )
    assert res["updated"] == 2
    assert await tags() == {"1": ["y"], "2": ["x", "y"]}


@pytest.mark.anyio
async def test_api_update_by_query(client, index_docs, user):
    async def cats():
        res = await query_documents(index_docs, fields=[FieldSpec(name="cat"), FieldSpec(name="subcat")])
        return {doc["_id"]: doc.get("subcat") for doc in (res.data if res else [])}

    # Delete requires WRITER privs
    await create_project_role(user, index_docs, Roles.READER)

    res = await client.post(
        f"/index/{index_docs}/update_by_query",
        json=dict(field="subcat", value="z", filters=dict(cat="a")),
        cookies=auth_cookie(user=user),
    )
    assert res.status_code == 403

    await update_project_role(user, index_docs, Roles.WRITER)
    res = await client.post(
        f"/index/{index_docs}/update_by_query",
        json=dict(field="subcat", value="z", filters=dict(cat="a")),
        cookies=auth_cookie(user=user),
    )
    res.raise_for_status()
    assert await cats() == {"0": "z", "1": "z", "2": "z", "3": "y"}


@pytest.mark.anyio
async def test_api_delete_by_query(client, index_docs, user):
    async def ids():
        await refresh_index(index_docs)
        res = await query_documents(index_docs)
        return {doc["_id"] for doc in (res.data if res else [])}

    # Delete requires WRITER privs
    await create_project_role(user, index_docs, Roles.READER)
    res = await client.post(
        f"/index/{index_docs}/delete_by_query",
        json=dict(filters=dict(cat="a")),
        cookies=auth_cookie(user=user),
    )
    assert res.status_code == 403

    await update_project_role(user, index_docs, Roles.WRITER)
    res = await client.post(
        f"/index/{index_docs}/delete_by_query",
        json=dict(filters=dict(cat="a")),
        cookies=auth_cookie(user=user),
    )
    res.raise_for_status()
    assert await ids() == {"3"}
