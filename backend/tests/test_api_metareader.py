import pytest
from httpx import AsyncClient

from amcat4.models import FieldSpec, SnippetParams
from tests.tools import auth_cookie, post_json


async def create_index_metareader(client, index, admin):
    await client.post(
        f"/index/{index}/users", cookies=auth_cookie(admin), json={"email": "meta@reader.com", "role": "METAREADER"}
    )


async def set_metareader_access(client, index, admin, metareader):
    await client.put(
        f"/index/{index}/fields",
        cookies=auth_cookie(admin),
        json={"text": {"metareader": metareader}},
    )


async def check_allowed(client, index: str, field: FieldSpec, allowed=True):
    await post_json(
        client,
        f"/index/{index}/query",
        user="meta@reader.com",
        expected=200 if allowed else 403,
        json={"fields": [field.model_dump()]},
    )


@pytest.mark.anyio
async def test_metareader_none(client: AsyncClient, admin, index_docs):
    """
    Set text field to metareader_access=none
    Metareader should not be able to get field both full and as snippet
    """
    await create_index_metareader(client, index_docs, admin)
    await set_metareader_access(client, index_docs, admin, {"access": "none"})

    full = FieldSpec(name="text")
    snippet = FieldSpec(name="text", snippet=SnippetParams(nomatch_words=150, max_matches=3, words_per_match=50))

    await check_allowed(client, index_docs, full, allowed=False)
    await check_allowed(client, index_docs, field=snippet, allowed=False)


@pytest.mark.anyio
async def test_metareader_read(client: AsyncClient, admin, index_docs):
    """
    Set text field to metareader_access=read
    Metareader should be able to get field both full and as snippet
    """
    await create_index_metareader(client, index_docs, admin)
    await set_metareader_access(client, index_docs, admin, {"access": "read"})

    full = FieldSpec(name="text")
    snippet = FieldSpec(name="text", snippet=SnippetParams(nomatch_words=150, max_matches=3, words_per_match=50))

    await check_allowed(client, index_docs, field=full, allowed=True)
    await check_allowed(client, index_docs, field=snippet, allowed=True)


@pytest.mark.anyio
async def test_metareader_aggregation(client: AsyncClient, admin, index_docs):
    """
    Test that metareader users can use fields they have access to for aggregation
    """
    await create_index_metareader(client, index_docs, admin)
    await client.put(
        f"/index/{index_docs}/fields",
        cookies=auth_cookie(admin),
        json={"cat": {"metareader": {"access": "read"}}},
    )
    await client.put(
        f"/index/{index_docs}/fields",
        cookies=auth_cookie(admin),
        json={"text": {"metareader": {"access": "none"}}},
    )
    response = await post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user="meta@reader.com",
        expected=200,
        json={"axes": [{"field": "cat"}]},
    )
    assert "data" in response
    assert any(item.get("cat") == "a" for item in response["data"])

    # But metareader should not be able to aggregate on "text" field
    response = await client.post(
        f"/index/{index_docs}/aggregate",
        cookies=auth_cookie("meta@reader.com"),
        json={"axes": [{"field": "text"}]},
    )
    assert response.status_code == 403
    assert "cannot see field text" in response.json()["detail"].lower()

    # Metareader should be able to use aggregation functions on fields they have access to
    await client.put(
        f"/index/{index_docs}/fields",
        cookies=auth_cookie(admin),
        json={"i": {"metareader": {"access": "read"}}},
    )
    response = await post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user="meta@reader.com",
        expected=200,
        json={"aggregations": [{"field": "i", "function": "avg"}]},
    )
    assert "data" in response
    assert "avg_i" in response["data"][0]

    # But not on fields they have no access
    await client.put(
        f"/index/{index_docs}/fields",
        cookies=auth_cookie(admin),
        json={"i": {"metareader": {"access": "none"}}},
    )
    response = await client.post(
        f"/index/{index_docs}/aggregate",
        cookies=auth_cookie("meta@reader.com"),
        json={"aggregations": [{"field": "i", "function": "avg"}]},
    )
    assert response.status_code == 403
    assert "cannot see field i" in response.json()["detail"].lower()


@pytest.mark.anyio
async def test_metareader_field_stats(client: AsyncClient, admin, index_docs):
    """
    Test that metareader users can get field statistics for fields they have access to
    """
    await create_index_metareader(client, index_docs, admin)

    await client.put(
        f"/index/{index_docs}/fields",
        cookies=auth_cookie(admin),
        json={"i": {"metareader": {"access": "read"}}},
    )
    await client.put(
        f"/index/{index_docs}/fields",
        cookies=auth_cookie(admin),
        json={"date": {"metareader": {"access": "none"}}},
    )
    response = await client.get(
        f"/index/{index_docs}/fields/i/stats",
        cookies=auth_cookie("meta@reader.com"),
    )
    assert response.status_code == 200
    stats = response.json()
    assert "count" in stats
    assert "min" in stats
    assert "max" in stats
    assert "avg" in stats

    # Metareader should not be able to get stats for "date" field
    response = await client.get(
        f"/index/{index_docs}/fields/date/stats",
        cookies=auth_cookie("meta@reader.com"),
    )
    assert response.status_code == 403
    assert "cannot access field date" in response.json()["detail"].lower()


@pytest.mark.anyio
async def test_metareader_snippet(client: AsyncClient, admin, index_docs):
    """
    Set text field to metareader_access=snippet[50;1;20]
    Metareader should only be able to get field as snippet
    with maximum parameters of nomatch_words=50, max_matches=1, words_per_match=20
    """
    await create_index_metareader(client, index_docs, admin)
    await set_metareader_access(
        client,
        index_docs,
        admin,
        {"access": "snippet", "max_snippet": {"nomatch_words": 50, "max_matches": 1, "words_per_match": 20}},
    )

    full = FieldSpec(name="text")
    S = SnippetParams
    snippet_too_long = FieldSpec(name="text", snippet=S(nomatch_words=51, max_matches=1, words_per_match=20))
    snippet_too_many_matches = FieldSpec(
        name="text", snippet=SnippetParams(nomatch_words=50, max_matches=2, words_per_match=20)
    )
    snippet_too_long_matches = FieldSpec(
        name="text", snippet=SnippetParams(nomatch_words=50, max_matches=1, words_per_match=21)
    )

    snippet_just_right = FieldSpec(name="text", snippet=S(nomatch_words=50, max_matches=1, words_per_match=20))
    snippet_less_than_allowed = FieldSpec(
        name="text", snippet=SnippetParams(nomatch_words=49, max_matches=0, words_per_match=19)
    )

    await check_allowed(client, index_docs, field=full, allowed=False)
    await check_allowed(client, index_docs, field=snippet_too_long, allowed=False)
    await check_allowed(client, index_docs, field=snippet_too_many_matches, allowed=False)
    await check_allowed(client, index_docs, field=snippet_too_long_matches, allowed=False)

    await check_allowed(client, index_docs, field=snippet_just_right, allowed=True)
    await check_allowed(client, index_docs, field=snippet_less_than_allowed, allowed=True)


@pytest.mark.anyio
async def test_visible_and_queryable(client: AsyncClient, admin, index_docs):
    """Fields can be visible but not queryable, or queryable but not visible (e.g. for non-consumptive research)"""
    await client.post(f"/index/{index_docs}/users", cookies=auth_cookie(admin), json={"email": "r@x.com", "role": "READER"})

    async def query(json, expected=200):
        return await post_json(client, f"/index/{index_docs}/query", user="r@x.com", expected=expected, json=json)

    # Text is not visible to readers, but can be queried
    r = await client.put(
        f"/index/{index_docs}/fields",
        cookies=auth_cookie(admin),
        json={"text": {"reader": {"visible": False, "queryable": True}}},
    )
    assert r.status_code == 204, r.text
    await query({"fields": ["text"]}, expected=403)
    r = await query({"queries": {"q": "text:test"}, "fields": ["cat"]})
    assert {d["_id"] for d in r["results"]} == {"1", "2"}

    # Title is visible, but cannot be queried
    r = await client.put(
        f"/index/{index_docs}/fields",
        cookies=auth_cookie(admin),
        json={"title": {"reader": {"visible": True, "queryable": False}}},
    )
    assert r.status_code == 204, r.text
    r = await query({"fields": ["title"]})
    assert any("title" in d for d in r["results"])
    r = await client.post(f"/index/{index_docs}/query", cookies=auth_cookie("r@x.com"), json={"queries": {"q": "title:title"}})
    assert r.status_code == 400 and "title" in r.text

    # The single document endpoint also hides invisible fields
    r = await client.get(f"/index/{index_docs}/documents/1", cookies=auth_cookie("r@x.com"))
    assert r.status_code == 200 and "text" not in r.json() and "title" in r.json()
