from fastapi.testclient import TestClient

from tests.tools import get_json, build_headers, post_json


def create_index_metareader(client, index, admin):
    # Create new user and set index role to metareader
    client.post(
        f"/users",
        headers=build_headers(admin),
        json={"email": "meta@reader.com", "role": "METAREADER"},
    ),
    client.put(
        f"/index/{index}/users/meta@reader.com",
        headers=build_headers(admin),
        json={"role": "METAREADER"},
    ),


def set_metareader_access(client, index, admin, access):
    client.post(
        f"/index/{index}/fields",
        headers=build_headers(admin),
        json={"text": {"type": "text", "meta": {"metareader_access": access}}},
    )


def check_allowed(client, index, field=None, snippet=None, allowed=True):
    params = {}
    body = {}

    if field:
        params["fields"] = field
        body["fields"] = [field]
    if snippet:
        params["snippets"] = snippet
        body["snippets"] = [snippet]

    get_json(
        client,
        f"/index/{index}/documents",
        user="meta@reader.com",
        expected=200 if allowed else 401,
        params=params,
    )
    post_json(
        client,
        f"/index/{index}/query",
        user="meta@reader.com",
        expected=200 if allowed else 401,
        json=body,
    )


def test_metareader_none(client: TestClient, admin, index_docs):
    """
    Set text field to metareader_access=none
    Metareader should not be able to get field both full and as snippet
    """
    create_index_metareader(client, index_docs, admin)
    set_metareader_access(client, index_docs, admin, "none")
    check_allowed(client, index_docs, field="text", allowed=False)
    check_allowed(client, index_docs, snippet="text", allowed=False)


def test_metareader_read(client: TestClient, admin, index_docs):
    """
    Set text field to metareader_access=read
    Metareader should be able to get field both full and as snippet
    """
    create_index_metareader(client, index_docs, admin)
    set_metareader_access(client, index_docs, admin, "read")
    check_allowed(client, index_docs, field="text", allowed=True)
    check_allowed(client, index_docs, snippet="text", allowed=True)


def test_metareader_snippet(client: TestClient, admin, index_docs):
    """
    Set text field to metareader_access=snippet
    Meta reader should be able to get field as snippet, but not full
    """
    create_index_metareader(client, index_docs, admin)

    set_metareader_access(client, index_docs, admin, "snippet")
    check_allowed(client, index_docs, field="text", allowed=False)
    check_allowed(client, index_docs, snippet="text", allowed=True)


def test_metareader_snippet_params(client: TestClient, admin, index_docs):
    """
    Set text field to metareader_access=snippet[50;1;20]
    Metareader should only be able to get field as snippet
    with maximum parameters of nomatch_chars=50, max_matches=1, match_chars=20
    """
    create_index_metareader(client, index_docs, admin)

    set_metareader_access(client, index_docs, admin, "snippet[50;1;20]")
    check_allowed(client, index_docs, field="text", allowed=False)
    check_allowed(client, index_docs, snippet="text", allowed=False)
    check_allowed(client, index_docs, snippet="text[51;1;20]", allowed=False)
    check_allowed(client, index_docs, snippet="text[50,1,20]", allowed=True)
    check_allowed(client, index_docs, snippet="text[49;1;20]", allowed=True)
