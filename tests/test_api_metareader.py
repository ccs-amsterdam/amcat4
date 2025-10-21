from fastapi.testclient import TestClient
from amcat4.models import FieldSpec, SnippetParams

from amcat4.systemdata.roles import set_project_guest_role
from tests.tools import build_headers, post_json


def create_index_metareader(client, index, admin):
    res = client.post(
        f"/index/{index}/users", headers=build_headers(admin), json={"email": "meta@reader.com", "role": "METAREADER"}
    )


def set_metareader_access(client, index, admin, metareader):
    client.put(
        f"/index/{index}/fields",
        headers=build_headers(admin),
        json={"text": {"metareader": metareader}},
    )


def check_allowed(client, index: str, field: FieldSpec, allowed=True):
    post_json(
        client,
        f"/index/{index}/query",
        user="meta@reader.com",
        expected=200 if allowed else 403,
        json={"fields": [field.model_dump()]},
    )


def test_metareader_none(client: TestClient, admin, index_docs):
    """
    Set text field to metareader_access=none
    Metareader should not be able to get field both full and as snippet
    """
    create_index_metareader(client, index_docs, admin)
    set_metareader_access(client, index_docs, admin, {"access": "none"})

    full = FieldSpec(name="text")
    snippet = FieldSpec(name="text", snippet=SnippetParams(nomatch_chars=150, max_matches=3, match_chars=50))

    check_allowed(client, index_docs, full, allowed=False)
    check_allowed(client, index_docs, field=snippet, allowed=False)


def test_metareader_read(client: TestClient, admin, index_docs):
    """
    Set text field to metareader_access=read
    Metareader should be able to get field both full and as snippet
    """
    create_index_metareader(client, index_docs, admin)
    set_metareader_access(client, index_docs, admin, {"access": "read"})

    full = FieldSpec(name="text")
    snippet = FieldSpec(name="text", snippet=SnippetParams(nomatch_chars=150, max_matches=3, match_chars=50))

    check_allowed(client, index_docs, field=full, allowed=True)
    check_allowed(client, index_docs, field=snippet, allowed=True)


def test_metareader_aggregation(client: TestClient, admin, index_docs):
    """
    Test that metareader users can use fields they have access to for aggregation
    """
    create_index_metareader(client, index_docs, admin)
    client.put(
        f"/index/{index_docs}/fields",
        headers=build_headers(admin),
        json={"cat": {"metareader": {"access": "read"}}},
    )
    client.put(
        f"/index/{index_docs}/fields",
        headers=build_headers(admin),
        json={"text": {"metareader": {"access": "none"}}},
    )
    response = post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user="meta@reader.com",
        expected=200,
        json={"axes": [{"field": "cat"}]},
    )
    assert "data" in response
    assert any(item.get("cat") == "a" for item in response["data"])

    # But metareader should not be able to aggregate on "text" field
    response = client.post(
        f"/index/{index_docs}/aggregate",
        headers=build_headers("meta@reader.com"),
        json={"axes": [{"field": "text"}]},
    )
    assert response.status_code == 403
    assert "metareader cannot read text" in response.json()["detail"].lower()

    # Metareader should be able to use aggregation functions on fields they have access to
    client.put(
        f"/index/{index_docs}/fields",
        headers=build_headers(admin),
        json={"i": {"metareader": {"access": "read"}}},
    )
    response = post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user="meta@reader.com",
        expected=200,
        json={"aggregations": [{"field": "i", "function": "avg"}]},
    )
    assert "data" in response
    assert "avg_i" in response["data"][0]

    # But not on fields they have no access
    client.put(
        f"/index/{index_docs}/fields",
        headers=build_headers(admin),
        json={"i": {"metareader": {"access": "none"}}},
    )
    response = client.post(
        f"/index/{index_docs}/aggregate",
        headers=build_headers("meta@reader.com"),
        json={"aggregations": [{"field": "i", "function": "avg"}]},
    )
    assert response.status_code == 403
    assert "metareader cannot read i" in response.json()["detail"].lower()


def test_metareader_field_stats(client: TestClient, admin, index_docs):
    """
    Test that metareader users can get field statistics for fields they have access to
    """
    create_index_metareader(client, index_docs, admin)

    client.put(
        f"/index/{index_docs}/fields",
        headers=build_headers(admin),
        json={"i": {"metareader": {"access": "read"}}},
    )
    client.put(
        f"/index/{index_docs}/fields",
        headers=build_headers(admin),
        json={"date": {"metareader": {"access": "none"}}},
    )
    response = client.get(
        f"/index/{index_docs}/fields/i/stats",
        headers=build_headers("meta@reader.com"),
    )
    assert response.status_code == 200
    stats = response.json()
    assert "count" in stats
    assert "min" in stats
    assert "max" in stats
    assert "avg" in stats

    # Metareader should not be able to get stats for "date" field
    response = client.get(
        f"/index/{index_docs}/fields/date/stats",
        headers=build_headers("meta@reader.com"),
    )
    assert response.status_code == 403
    assert "metareader cannot" in response.json()["detail"].lower()


def test_metareader_snippet(client: TestClient, admin, index_docs):
    """
    Set text field to metareader_access=snippet[50;1;20]
    Metareader should only be able to get field as snippet
    with maximum parameters of nomatch_chars=50, max_matches=1, match_chars=20
    """
    create_index_metareader(client, index_docs, admin)
    set_metareader_access(
        client,
        index_docs,
        admin,
        {"access": "snippet", "max_snippet": {"nomatch_chars": 50, "max_matches": 1, "match_chars": 20}},
    )

    full = FieldSpec(name="text")
    snippet_too_long = FieldSpec(name="text", snippet=SnippetParams(nomatch_chars=51, max_matches=1, match_chars=20))
    snippet_too_many_matches = FieldSpec(name="text", snippet=SnippetParams(nomatch_chars=50, max_matches=2, match_chars=20))
    snippet_too_long_matches = FieldSpec(name="text", snippet=SnippetParams(nomatch_chars=50, max_matches=1, match_chars=21))

    snippet_just_right = FieldSpec(name="text", snippet=SnippetParams(nomatch_chars=50, max_matches=1, match_chars=20))
    snippet_less_than_allowed = FieldSpec(name="text", snippet=SnippetParams(nomatch_chars=49, max_matches=0, match_chars=19))

    check_allowed(client, index_docs, field=full, allowed=False)
    check_allowed(client, index_docs, field=snippet_too_long, allowed=False)
    check_allowed(client, index_docs, field=snippet_too_many_matches, allowed=False)
    check_allowed(client, index_docs, field=snippet_too_long_matches, allowed=False)

    check_allowed(client, index_docs, field=snippet_just_right, allowed=True)
    check_allowed(client, index_docs, field=snippet_less_than_allowed, allowed=True)
