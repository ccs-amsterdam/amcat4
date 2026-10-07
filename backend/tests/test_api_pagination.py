import pytest

from amcat4.models import CreateDocumentField
from amcat4.systemdata.roles import Roles, create_project_role
from tests.conftest import upload
from tests.tools import post_json


@pytest.mark.anyio
async def test_pagination(client, index, user):
    """Does basic pagination work?"""
    await create_project_role(user, index, Roles.READER)

    # TODO. Tests are not independent. test_pagination fails if run directly after other tests.
    # Probably delete_index doesn't fully delete

    await upload(index, docs=[{"i": i} for i in range(66)], fields={"i": "integer"})
    url = f"/index/{index}/query"
    r = await post_json(client, url, user=user, json={"sort": "i", "per_page": 20, "fields": ["i"]}, expected=200)

    assert r["meta"]["per_page"] == 20
    assert r["meta"]["page"] == 0
    assert r["meta"]["page_count"] == 4
    assert {h["i"] for h in r["results"]} == set(range(20))
    r = await post_json(client, url, user=user, json={"sort": "i", "per_page": 20, "page": 3, "fields": ["i"]}, expected=200)
    assert r["meta"]["page"] == 3
    assert {h["i"] for h in r["results"]} == {60, 61, 62, 63, 64, 65}
    r = await post_json(client, url, user=user, json={"sort": "i", "per_page": 20, "page": 4, "fields": ["i"]}, expected=200)
    assert len(r["results"]) == 0


@pytest.mark.anyio
async def test_cursor(client, index, user):
    await create_project_role(user, index, Roles.READER)
    await upload(index, docs=[{"i": i} for i in range(66)], fields={"i": CreateDocumentField(type="integer")})
    url = f"/index/{index}/query"
    body = {"sort": [{"i": {"order": "desc"}}], "per_page": 30, "fields": ["i"]}
    r = await post_json(client, url, user=user, json=body, expected=200)
    assert {h["i"] for h in r["results"]} == set(range(36, 66))
    r = await post_json(client, url, user=user, json={**body, "after": r["meta"]["next"]}, expected=200)
    assert {h["i"] for h in r["results"]} == set(range(6, 36))
    r = await post_json(client, url, user=user, json={**body, "after": r["meta"]["next"]}, expected=200)
    assert {h["i"] for h in r["results"]} == set(range(6))
    assert r["meta"]["next"] is None

    # Without sort, the cursor uses the internal id
    body = {"per_page": 30, "fields": ["i"]}
    r = await post_json(client, url, user=user, json=body, expected=200)
    seen = [h["i"] for h in r["results"]]
    while r["meta"]["next"]:
        r = await post_json(client, url, user=user, json={**body, "after": r["meta"]["next"]}, expected=200)
        seen += [h["i"] for h in r["results"]]
    assert sorted(seen) == list(range(66))
