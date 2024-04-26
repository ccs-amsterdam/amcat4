import asyncio
import json
import logging
import httpx
import pytest

from amcat4.index import Role, add_instruction, get_document, refresh_index, set_role
from amcat4.preprocessing.models import PreprocessingInstruction
from amcat4.preprocessing.processor import get_manager
from tests.conftest import TEST_DOCUMENTS
from tests.test_preprocessing import INSTRUCTION
from tests.tools import aget_json, build_headers, check, get_json

logger = logging.getLogger("amcat4.tests")


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
    i = PreprocessingInstruction.model_validate_json(json.dumps(INSTRUCTION))

    set_role(index_docs, user, Role.WRITER)
    res = client.get(f"/index/{index_docs}/preprocessing", headers=build_headers(user=user))
    res.raise_for_status()
    assert len(res.json()) == 0

    httpx_mock.add_response(url=i.endpoint, json={"labels": ["games", "sports"], "scores": [0.9, 0.1]})

    res = client.post(f"/index/{index_docs}/preprocessing", headers=build_headers(user=user), json=i.model_dump())
    res.raise_for_status()
    refresh_index(index_docs)
    res = client.get(f"/index/{index_docs}/preprocessing", headers=build_headers(user=user))
    res.raise_for_status()
    assert {item["field"] for item in res.json()} == {i.field}

    while len(httpx_mock.get_requests()) < len(TEST_DOCUMENTS):
        await asyncio.sleep(0.1)
    await asyncio.sleep(0.1)
    assert all(get_document(index_docs, doc["_id"])["class_label"] == "games" for doc in TEST_DOCUMENTS)

    # Cannot re-add the same field
    check(client.post(f"/index/{index_docs}/preprocessing", json=i.model_dump(), headers=build_headers(user=user)), 400)


@pytest.mark.asyncio
async def test_pause_restart(aclient: httpx.AsyncClient, admin, index_docs, httpx_mock, caplog):
    async def slow_response(request):
        json.loads(request.content)["inputs"]
        await asyncio.sleep(0.1)
        return httpx.Response(json={"labels": ["politics"], "scores": [1]}, status_code=200)

    i = PreprocessingInstruction.model_validate_json(json.dumps(INSTRUCTION))
    httpx_mock.add_callback(slow_response, url=i.endpoint)
    status_url = f"/index/{index_docs}/preprocessing/{i.field}/status"

    # Start the preprocessor, wait .15 seconds
    add_instruction(index_docs, i)
    await asyncio.sleep(0.15)

    assert (await aget_json(aclient, status_url, user=admin))["status"] == "Active"

    # Set the processor to pause
    check(await aclient.post(status_url, json=dict(action="Stop"), headers=build_headers(user=admin)), 204)
    await asyncio.sleep(0)
    assert (await aget_json(aclient, status_url, user=admin))["status"] == "Stopped"

    # Some, but not all docs should be done yet
    assert len(httpx_mock.get_requests()) < len(TEST_DOCUMENTS)
    assert len(httpx_mock.get_requests()) > 0

    # Restart processor
    check(await aclient.post(status_url, json=dict(action="Start"), headers=build_headers(user=admin)), 204)
    await asyncio.sleep(0)
    assert (await aget_json(aclient, status_url, user=admin))["status"] == "Active"

    await get_manager().running_tasks[index_docs, i.field]
    assert (await aget_json(aclient, status_url, user=admin))["status"] == "Done"

    # There should be at most one extra request (the cancelled one)
    assert len(httpx_mock.get_requests()) <= len(TEST_DOCUMENTS) + 1


@pytest.mark.asyncio
async def test_reassign_error(aclient: httpx.AsyncClient, admin, index_docs, httpx_mock):
    async def mistakes_were_made(request):
        await asyncio.sleep(0.1)
        input = json.loads(request.content)["inputs"]
        if "text" in input:  # should be true for 2 documents
            return httpx.Response(json={"kettle": "black"}, status_code=418)
        else:
            return httpx.Response(json={"labels": ["first pass"]}, status_code=200)

    i = PreprocessingInstruction.model_validate_json(json.dumps(INSTRUCTION))
    httpx_mock.add_callback(mistakes_were_made, url=i.endpoint)

    # Start the preprocessor, wait .15 seconds
    add_instruction(index_docs, i)
    await get_manager().running_tasks[index_docs, i.field]
    field_url = f"/index/{index_docs}/preprocessing/{i.field}"
    status_url = f"{field_url}/status"

    res = await aget_json(aclient, field_url, user=admin)
    assert res["status"] == "Done"
    assert res["counts"] == {"total": 4, "done": 2, "error": 2}

    httpx_mock.reset(True)
    httpx_mock.add_response(url=i.endpoint, json={"labels": ["secondpass"]})

    check(await aclient.post(status_url, json=dict(action="Reassign"), headers=build_headers(user=admin)), 204)
    await get_manager().running_tasks[index_docs, i.field]

    res = await aget_json(aclient, field_url, user=admin)
    assert res["status"] == "Done"
    assert res["counts"] == {"total": 4, "done": 4}

    # Check that only error'd documents are reassigned
    assert len(httpx_mock.get_requests()) == 2
