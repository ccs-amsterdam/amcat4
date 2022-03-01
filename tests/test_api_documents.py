from amcat4.auth import Role
from tests.tools import post_json, build_headers, get_json


def test_documents_unauthorized(client, index, user):
    """Anonymous and unauthorized user cannot get, put, or post documents"""
    assert client.post(f"index/{index.name}/documents") == 401
    assert client.post(f"index/{index.name}/documents", headers=build_headers(user=user)) == 401
    assert client.put(f"index/{index.name}/documents/1") == 401
    assert client.put(f"index/{index.name}/documents/1", headers=build_headers(user=user)) == 401
    assert client.get(f"index/{index.name}/documents/1") == 401
    assert client.get(f"index/{index.name}/documents/1", headers=build_headers(user=user)) == 401


def test_documents(client, index, user):
    """Test uploading, modifying, deleting, and retrieving documents"""
    index.set_role(user, Role.WRITER)
    r = post_json(client, f"index/{index.name}/documents", user=user,
                  json={"documents": [{"title": "a title", "text": "text", "date": "2020-01-01"}]})
    assert len(r) == 1
    url = f"index/{index.name}/documents/{r[0]}"
    assert get_json(client, url, user=user)["title"] == "a title"
    assert client.put(url, json={"title": "the headline"}, headers=build_headers(user)) == 204
    assert get_json(client, url, user=user)["title"] == "the headline"
    assert client.delete(url, headers=build_headers(user)) == 204
    assert client.get(url, headers=build_headers(user)) == 404
