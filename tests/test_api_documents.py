from turtle import pos
from amcat4.index import set_role, Role
from tests.conftest import index_docs, populate_index
from tests.tools import post_json, build_headers, get_json, check


def test_documents_unauthorized(client, index, user):
    """Anonymous and unauthorized user cannot get, put, or post documents"""
    docs = {"documents": []}
    check(client.post(f"index/{index}/documents", json=docs), 401)
    check(
        client.post(
            f"index/{index}/documents", json=docs, headers=build_headers(user=user)
        ),
        401,
    )
    check(client.put(f"index/{index}/documents/1", json={}), 401)
    check(
        client.put(
            f"index/{index}/documents/1", json={}, headers=build_headers(user=user)
        ),
        401,
    )
    check(client.get(f"index/{index}/documents/1"), 401)
    check(
        client.get(f"index/{index}/documents/1", headers=build_headers(user=user)), 401
    )


def test_documents(client, index, user):
    """Test uploading, modifying, deleting, and retrieving documents"""
    set_role(index, user, Role.WRITER)
    post_json(
        client,
        f"index/{index}/documents",
        user=user,
        json={
            "documents": [
                {"_id": "id", "title": "a title", "text": "text", "date": "2020-01-01"}
            ]
        },
    )
    url = f"index/{index}/documents/id"
    assert get_json(client, url, user=user)["title"] == "a title"
    check(
        client.put(url, json={"title": "the headline"}, headers=build_headers(user)),
        204,
    )
    assert get_json(client, url, user=user)["title"] == "the headline"
    check(client.delete(url, headers=build_headers(user)), 204)
    check(client.get(url, headers=build_headers(user)), 404)


def test_metareader(client, index, index_docs, user, reader):
    set_role(index, user, Role.METAREADER)
    set_role(index, reader, Role.READER)
    populate_index(index)

    r = get_json(
        client,
        f"/index/{index}/documents?fields=title",
        headers=build_headers(user),
    )
    _id = r["results"][0]["_id"]
    url = f"index/{index}/documents/{_id}"
    # Metareader should not be able to retrieve document source
    check(client.get(url, headers=build_headers(user)), 401)
    check(client.get(url, headers=build_headers(reader)), 200)

    def get_join(x):
        return ",".join(x) if isinstance(x, list) else x

    # Metareader should not be able to query text (including highlight)
    for ix, u, fields, highlight, outcome in [
        (index, user, ["text"], False, 401),
        (index_docs, user, ["text"], False, 200),
        ([index_docs, index], user, ["text"], False, 401),
        (index, user, ["text", "title"], False, 401),
        (index, user, ["title"], False, 200),
        (index, reader, ["text"], False, 200),
        ([index_docs, index], reader, ["text"], False, 200),
        (index, user, ["title"], True, 401),
        (index, reader, ["title"], True, 200),
    ]:
        check(
            client.get(
                f"/index/{get_join(ix)}/documents?fields={get_join(fields)}{'&highlight=true' if highlight else ''}",
                headers=build_headers(u),
            ),
            outcome,
            msg=f"Index: {ix}, user: {u}, fields: {fields}",
        )
        body = {"fields": fields}
        if highlight:
            body["highlight"] = True
        check(
            client.post(
                f"/index/{get_join(ix)}/query",
                headers=build_headers(u),
                json=body,
            ),
            outcome,
            msg=f"Index: {ix}, user: {u}, fields: {fields}",
        )
