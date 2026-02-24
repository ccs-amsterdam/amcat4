import pytest

from amcat4.models import Roles
from amcat4.systemdata.roles import update_project_role
from tests.tools import adelete, auth_cookie, get_json, post_json, put_json


@pytest.mark.anyio
async def test_documents_unauthorized(client, index, user):
    """Anonymous and unauthorized user cannot get, put, or post documents"""
    docs = {"documents": []}
    await post_json(client, f"index/{index}/documents", json=docs, expected=403)
    await post_json(client, f"index/{index}/documents", json=docs, cookies=auth_cookie(user=user), expected=403)
    await put_json(client, f"index/{index}/documents/1", json={}, expected=403)
    await put_json(client, f"index/{index}/documents/1", json={}, cookies=auth_cookie(user=user), expected=403)
    await get_json(client, f"index/{index}/documents/1", expected=403)
    await get_json(client, f"index/{index}/documents/1", cookies=auth_cookie(user=user), expected=403)


@pytest.mark.anyio
async def test_documents(client, index, user):
    """Test uploading, modifying, deleting, and retrieving documents"""
    await update_project_role(user, index, Roles.WRITER, ignore_missing=True)
    await post_json(
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
    assert (await get_json(client, url, user=user))["title"] == "a title"
    await put_json(client, url, json={"title": "the headline"}, cookies=auth_cookie(user), expected=204)
    assert (await get_json(client, url, user=user))["title"] == "the headline"
    await adelete(client, url, cookies=auth_cookie(user), expected=204)
    await get_json(client, url, cookies=auth_cookie(user), expected=404)
