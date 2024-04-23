import asyncio
import time
import httpx
from pytest_httpx import HTTPXMock
import json

import pytest
from amcat4.fields import create_fields
from amcat4.index import get_document, reassign_preprocessing_errors, refresh_index, upload_documents, add_instruction
from amcat4.preprocessing.models import PreprocessingInstruction
from amcat4.preprocessing import processor

from amcat4.preprocessing.processor import (
    get_counts,
    get_manager,
    get_todo,
    process_doc,
    process_documents,
)
from tests.conftest import TEST_DOCUMENTS

INSTRUCTION = dict(
    field="preprocess_label",
    task="HuggingFace Zero-Shot",
    endpoint="https://api-inference.huggingface.co/models/facebook/bart-large-mnli",
    arguments=[{"name": "input", "field": "text"}, {"name": "candidate_labels", "value": ["politics", "sports"]}],
    outputs=[{"name": "label", "field": "class_label"}],
)


def test_build_request(index):
    i = PreprocessingInstruction.model_validate_json(json.dumps(INSTRUCTION))
    doc = dict(text="Sample text")
    req = i.build_request(index, doc)
    assert req.url == INSTRUCTION["endpoint"]
    assert json.loads(req.content) == dict(inputs=doc["text"], parameters=dict(candidate_labels=["politics", "sports"]))


def test_parse_result():
    i = PreprocessingInstruction.model_validate_json(json.dumps(INSTRUCTION))
    output = {"labels": ["politics", "sports"], "scores": [0.9, 0.1]}
    update = dict(i.parse_output(output))
    assert update == dict(class_label="politics")


@pytest.mark.asyncio
async def test_preprocess(index_docs, httpx_mock: HTTPXMock):
    """Test logic of process_doc and get_todo calls"""
    i = PreprocessingInstruction.model_validate_json(json.dumps(INSTRUCTION))
    httpx_mock.add_response(url=i.endpoint, json={"labels": ["politics", "sports"], "scores": [0.9, 0.1]})

    # Create a preprocess fields. There should now be |docs| todo
    create_fields(index_docs, {i.field: "preprocess"})
    todos = list(get_todo(index_docs, i))
    assert all(set(todo.keys()) == {"_id", "text"} for todo in todos)
    assert {doc["_id"] for doc in todos} == {str(doc["_id"]) for doc in TEST_DOCUMENTS}

    # Process a single document. Check that it's done, and that the todo list is now one shorter
    todo = sorted(todos, key=lambda todo: todo["_id"])[0]
    await process_doc(index_docs, i, todo)
    doc = get_document(index_docs, todo["_id"])
    assert doc[i.field] == {"status": "done"}
    assert doc["class_label"] == "politics"
    refresh_index(index_docs)
    todos = list(get_todo(index_docs, i))
    assert {doc["_id"] for doc in todos} == {str(doc["_id"]) for doc in TEST_DOCUMENTS} - {todo["_id"]}

    # run a single preprocessing loop, check that done is False and that
    done = await process_documents(index_docs, i, size=2)
    assert done == False
    refresh_index(index_docs)
    todos = list(get_todo(index_docs, i))
    assert len(todos) == len(TEST_DOCUMENTS) - (2 + 1)

    # run preprocessing until it returns done = True
    while not done:
        done = await process_documents(index_docs, i, size=2)

    # Todo should be empty, and there should be one call per document!
    refresh_index(index_docs)
    todos = list(get_todo(index_docs, i))
    assert len(todos) == 0
    assert len(httpx_mock.get_requests()) == len(TEST_DOCUMENTS)


@pytest.mark.asyncio
async def test_preprocess_loop(index_docs, httpx_mock: HTTPXMock):
    """Test that adding an instruction automatically processes all docs in an index"""
    i = PreprocessingInstruction.model_validate_json(json.dumps(INSTRUCTION))
    httpx_mock.add_response(url=i.endpoint, json={"labels": ["politics", "sports"], "scores": [0.9, 0.1]})
    add_instruction(index_docs, i)
    await get_manager().running_tasks[index_docs, i.field]
    assert len(httpx_mock.get_requests()) == len(TEST_DOCUMENTS)
    assert all(get_document(index_docs, doc["_id"])["class_label"] == "politics" for doc in TEST_DOCUMENTS)


@pytest.mark.asyncio
async def test_preprocess_logic(index, httpx_mock: HTTPXMock):
    """Test that main processing loop works correctly"""
    i = PreprocessingInstruction.model_validate_json(json.dumps(INSTRUCTION))

    async def mock_slow_response(_request) -> httpx.Response:
        await asyncio.sleep(0.5)
        return httpx.Response(json={"labels": ["politics"], "scores": [1]}, status_code=200)

    httpx_mock.add_callback(mock_slow_response, url=i.endpoint)

    # Add the instruction. Since there are no documents, it should return instantly-ish
    add_instruction(index, i)
    await asyncio.sleep(0.1)
    assert get_manager().get_status(index, i.field) == "Stopped"

    # Add a document. The task should be re-activated and take half a second to complete
    upload_documents(index, [{"text": "text"}], fields={"text": "text"})
    await asyncio.sleep(0.1)
    assert get_manager().get_status(index, i.field) == "Active"
    await asyncio.sleep(0.5)
    assert get_manager().get_status(index, i.field) == "Stopped"


@pytest.mark.asyncio
async def test_preprocess_ratelimit(index_docs, httpx_mock: HTTPXMock):
    """Test that processing is paused on hitting rate limit, and restarts automatically"""
    i = PreprocessingInstruction.model_validate_json(json.dumps(INSTRUCTION))
    httpx_mock.add_response(url=i.endpoint, status_code=503)

    # Set a low pause time for the test
    processor.PAUSE_ON_RATE_LIMIT_SECONDS = 0.5

    # Start the async preprocessing loop. Receiving a 503 it should sleep for and retry
    add_instruction(index_docs, i)
    await asyncio.sleep(0.1)
    assert get_manager().get_status(index_docs, i.field) == "Paused"

    # Now mock a success response and wait for .5 seconds
    httpx_mock.reset(assert_all_responses_were_requested=True)
    httpx_mock.add_response(url=i.endpoint, json={"labels": ["politics", "sports"], "scores": [0.9, 0.1]})
    await asyncio.sleep(0.5)
    assert get_manager().get_status(index_docs, i.field) == "Stopped"


@pytest.mark.asyncio
async def test_preprocess_error(index_docs, httpx_mock: HTTPXMock):
    """Test that errors are reported correctly"""
    i = PreprocessingInstruction.model_validate_json(json.dumps(INSTRUCTION))

    def some_errors(request):
        input = json.loads(request.content)["inputs"]
        if "text" in input:  # should be true for 2 documents
            return httpx.Response(json={"error": "I'm a teapot!"}, status_code=418)
        else:
            return httpx.Response(json={"labels": ["politics"], "scores": [1]}, status_code=200)

    httpx_mock.add_callback(some_errors, url=i.endpoint)
    add_instruction(index_docs, i)
    await get_manager().running_tasks[index_docs, i.field]
    for doc in TEST_DOCUMENTS:
        result = get_document(index_docs, doc["_id"])
        assert result[i.field]["status"] == "error" if "text" in doc["text"] else "done"
    assert get_counts(index_docs, i.field) == dict(total=4, done=2, error=2)

    httpx_mock.reset(True)
    httpx_mock.add_response(url=i.endpoint, json={"labels": ["sports"], "scores": [1]})
    reassign_preprocessing_errors(index_docs, i.field)
    await get_manager().running_tasks[index_docs, i.field]
    for doc in TEST_DOCUMENTS:
        result = get_document(index_docs, doc["_id"])
        assert result[i.field]["status"] == "done"
        assert result["class_label"] == "sports" if "text" in doc["text"] else "politics"
    assert len(httpx_mock.get_requests()) == 2
