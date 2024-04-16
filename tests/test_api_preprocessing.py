import asyncio
import pytest
from amcat4.index import Role, get_document, refresh_index, set_role
from tests.conftest import TEST_DOCUMENTS
from tests.test_preprocessing import INSTRUCTION
from tests.tools import build_headers, check


def test_get_tasks(client):
    # UPDATE after we make a proper 'task store'
    res = client.get("/preprocessing_tasks")
    res.raise_for_status()
    assert any(task["name"] == "HuggingFace Zero-Shot" for task in res.json())


def test_auth(client, index, user):
    check(client.get(f"/index/{index}/preprocessing"), 401)
    check(client.post(f"/index/{index}/preprocessing", json=INSTRUCTION), 401)
    set_role(index, user, Role.READER)

    check(client.get(f"/index/{index}/preprocessing", headers=build_headers(user=user)), 200)
    check(client.post(f"/index/{index}/preprocessing", json=INSTRUCTION, headers=build_headers(user=user)), 401)


@pytest.mark.asyncio
async def test_post_get_instructions(client, user, index_docs, httpx_mock):
    set_role(index_docs, user, Role.WRITER)
    res = client.get(f"/index/{index_docs}/preprocessing", headers=build_headers(user=user))
    res.raise_for_status()
    assert len(res.json()) == 0

    httpx_mock.add_response(url=INSTRUCTION["endpoint"], json={"labels": ["games", "sports"], "scores": [0.9, 0.1]})

    res = client.post(f"/index/{index_docs}/preprocessing", headers=build_headers(user=user), json=INSTRUCTION)
    res.raise_for_status()
    refresh_index(index_docs)
    res = client.get(f"/index/{index_docs}/preprocessing", headers=build_headers(user=user))
    res.raise_for_status()
    assert {item["field"] for item in res.json()} == {INSTRUCTION["field"]}

    while len(httpx_mock.get_requests()) < len(TEST_DOCUMENTS):
        await asyncio.sleep(0.1)
    await asyncio.sleep(0.1)
    assert all(get_document(index_docs, doc["_id"])["class_label"] == "games" for doc in TEST_DOCUMENTS)

    # Cannot re-add the same field
    check(client.post(f"/index/{index_docs}/preprocessing", json=INSTRUCTION, headers=build_headers(user=user)), 400)
