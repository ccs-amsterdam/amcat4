from amcat4.index import Role, set_role
from amcat4.models import CreateField
from tests.conftest import upload
from tests.tools import get_json, post_json


def test_pagination(client, index, user):
    """Does basic pagination work?"""
    set_role(index, user, Role.READER)

    # TODO. Tests are not independent. test_pagination fails if run directly after other tests.
    # Probably delete_index doesn't fully delete

    upload(index, docs=[{"i": i} for i in range(66)], fields={"i": "integer"})
    url = f"/index/{index}/query"
    r = post_json(client, url, user=user, json={"sort": "i", "per_page": 20, "fields": ["i"]}, expected=200)

    assert r["meta"]["per_page"] == 20
    assert r["meta"]["page"] == 0
    assert r["meta"]["page_count"] == 4
    assert {h["i"] for h in r["results"]} == set(range(20))
    r = post_json(client, url, user=user, json={"sort": "i", "per_page": 20, "page": 3, "fields": ["i"]}, expected=200)
    assert r["meta"]["page"] == 3
    assert {h["i"] for h in r["results"]} == {60, 61, 62, 63, 64, 65}
    r = post_json(client, url, user=user, json={"sort": "i", "per_page": 20, "page": 4, "fields": ["i"]}, expected=200)
    assert len(r["results"]) == 0


def test_scroll(client, index, user):
    set_role(index, user, Role.READER)
    upload(index, docs=[{"i": i} for i in range(66)], fields={"i": CreateField(type="long")})
    url = f"/index/{index}/query"
    r = post_json(
        client,
        url,
        user=user,
        json={"scroll": "5m", "sort": [{"i": {"order": "desc"}}], "per_page": 30, "fields": ["i"]},
        expected=200,
    )

    scroll_id = r["meta"]["scroll_id"]
    assert scroll_id is not None
    assert {h["i"] for h in r["results"]} == set(range(36, 66))

    r = post_json(client, url, user=user, json={"scroll_id": scroll_id}, expected=200)
    assert {h["i"] for h in r["results"]} == set(range(6, 36))
    assert r["meta"]["scroll_id"] == scroll_id
    r = post_json(client, url, user=user, json={"scroll_id": scroll_id}, expected=200)
    assert {h["i"] for h in r["results"]} == set(range(6))

    # Scrolling past the edge should return 404
    post_json(client, url, user=user, json={"scroll_id": scroll_id}, expected=404)

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
