from amcat4.index import Role, set_role
from tests.conftest import upload
from tests.tools import get_json, post_json


def test_pagination(client, index, user):
    """Does basic pagination work?"""
    set_role(index, user, Role.READER)

    upload(index, docs=[{"i": i} for i in range(66)])
    url = f"/index/{index}/documents"
    r = get_json(
        client, url, user=user, params={"sort": "i", "per_page": 20, "fields": ["i"]}
    )
    assert r["meta"]["per_page"] == 20
    assert r["meta"]["page"] == 0
    assert r["meta"]["page_count"] == 4
    assert {h["i"] for h in r["results"]} == set(range(20))
    r = get_json(
        client,
        url,
        user=user,
        params={"sort": "i", "per_page": 20, "page": 3, "fields": ["i"]},
    )
    assert r["meta"]["page"] == 3
    assert {h["i"] for h in r["results"]} == {60, 61, 62, 63, 64, 65}
    r = get_json(
        client, url, user=user, params={"sort": "i", "per_page": 20, "page": 4}
    )
    assert len(r["results"]) == 0
    # Test POST query

    r = post_json(
        client,
        f"/index/{index}/query",
        expected=200,
        user=user,
        json={"sort": "i", "per_page": 20, "page": 3, "fields": ["i"]},
    )
    assert r["meta"]["page"] == 3
    assert {h["i"] for h in r["results"]} == {60, 61, 62, 63, 64, 65}


def test_scroll(client, index, user):
    set_role(index, user, Role.READER)
    upload(index, docs=[{"i": i} for i in range(66)])
    url = f"/index/{index}/documents"
    r = get_json(
        client,
        url,
        user=user,
        params={"sort": "i:desc", "per_page": 30, "scroll": "5m", "fields": ["i"]},
    )
    scroll_id = r["meta"]["scroll_id"]
    assert scroll_id is not None
    assert {h["i"] for h in r["results"]} == set(range(36, 66))
    r = get_json(client, url, user=user, params={"scroll_id": scroll_id})
    assert {h["i"] for h in r["results"]} == set(range(6, 36))
    assert r["meta"]["scroll_id"] == scroll_id
    r = get_json(client, url, user=user, params={"scroll_id": scroll_id})
    assert {h["i"] for h in r["results"]} == set(range(6))
    # Scrolling past the edge should return 404
    get_json(client, url, user=user, params={"scroll_id": scroll_id}, expected=404)
    # Test POST to query endpoint
    r = post_json(
        client,
        f"/index/{index}/query",
        user=user,
        expected=200,
        json={
            "sort": [{"i": {"order": "desc"}}],
            "per_page": 30,
            "scroll": "5m",
            "fields": ["i"],
        },
    )
    scroll_id = r["meta"]["scroll_id"]
    assert scroll_id is not None
    assert {h["i"] for h in r["results"]} == set(range(36, 66))
