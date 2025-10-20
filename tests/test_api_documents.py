from amcat4.models import Roles, User
from amcat4.systemdata.roles import get_user_project_role, update_project_role
from tests.tools import post_json, build_headers, get_json, check


def test_documents_unauthorized(client, index, user):
    """Anonymous and unauthorized user cannot get, put, or post documents"""
    docs = {"documents": []}
    check(client.post(f"index/{index}/documents", json=docs), 401)
    check(
        client.post(f"index/{index}/documents", json=docs, headers=build_headers(user=user)),
        401,
    )
    check(client.put(f"index/{index}/documents/1", json={}), 401)
    check(
        client.put(f"index/{index}/documents/1", json={}, headers=build_headers(user=user)),
        401,
    )
    check(client.get(f"index/{index}/documents/1"), 401)
    check(client.get(f"index/{index}/documents/1", headers=build_headers(user=user)), 401)


def test_documents(client, index, user):
    """Test uploading, modifying, deleting, and retrieving documents"""
    update_project_role(user, index, Roles.WRITER, ignore_missing=True)
    post_json(
        client,
        f"index/{index}/documents",
        user=user,
        json={
            "documents": [{"_id": "id", "title": "a title", "text": "text", "date": "2020-01-01"}],
            "fields": {
                "title": {"type": "text"},
                "text": {"type": "text"},
                "date": {"type": "date"},
            },
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
