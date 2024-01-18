from fastapi.testclient import TestClient
from amcat4.models import FieldSpec, SnippetParams

from tests.tools import build_headers, post_json


def create_index_metareader(client, index, admin):
    # Create new user and set index role to metareader
    client.post("/users", headers=build_headers(admin), json={"email": "meta@reader.com", "role": "METAREADER"}),
    client.put(f"/index/{index}/users/meta@reader.com", headers=build_headers(admin), json={"role": "METAREADER"}),


def set_metareader_access(client, index, admin, metareader):
    client.post(
        f"/index/{index}/fields",
        headers=build_headers(admin),
        json={"text": {"type": "text", "metareader": metareader}},
    )


def check_allowed(client, index: str, field: FieldSpec, allowed=True):
    post_json(
        client,
        f"/index/{index}/query",
        user="meta@reader.com",
        expected=200 if allowed else 401,
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
