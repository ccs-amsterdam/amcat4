from pytest_httpx import HTTPXMock
import json

import httpx
import pytest
import requests
from amcat4.fields import create_fields
from amcat4.index import get_document, refresh_index
from amcat4.preprocessing.instruction import PreprocessingInstruction
import responses

from amcat4.preprocessing.processor import get_todo, process_doc
from tests.conftest import TEST_DOCUMENTS

INSTRUCTION = dict(
    field="preprocess_label",
    task="HuggingFace Zero-Shot",
    endpoint="https://api-inference.huggingface.co/models/facebook/bart-large-mnli",
    arguments=[{"name": "input", "field": "text"}, {"name": "candidate_labels", "value": ["politics", "sports"]}],
    outputs=[{"name": "label", "field": "class_label"}],
)


def test_build_request():
    i = PreprocessingInstruction.model_validate_json(json.dumps(INSTRUCTION))
    doc = dict(text="Sample text")
    req = i.build_request(doc)
    assert req.url == INSTRUCTION["endpoint"]
    assert json.loads(req.content) == dict(inputs=doc["text"], parameters=dict(candidate_labels=["politics", "sports"]))


def test_parse_result():
    i = PreprocessingInstruction.model_validate_json(json.dumps(INSTRUCTION))
    output = {"labels": ["politics", "sports"], "scores": [0.9, 0.1]}
    update = dict(i.parse_output(output))
    assert update == dict(class_label="politics")


@pytest.mark.asyncio
async def test_preprocess(index_docs, httpx_mock: HTTPXMock):
    i = PreprocessingInstruction.model_validate_json(json.dumps(INSTRUCTION))
    create_fields(index_docs, {i.field: "preprocess"})
    todos = list(get_todo(index_docs, i))
    assert all(set(todo.keys()) == {"_id", "text"} for todo in todos)
    assert {doc["_id"] for doc in todos} == {str(doc["_id"]) for doc in TEST_DOCUMENTS}

    todo = sorted(todos, key=lambda todo: todo["_id"])[0]
    httpx_mock.add_response(url=i.endpoint, json={"labels": ["politics", "sports"], "scores": [0.9, 0.1]})
    await process_doc(index_docs, i, todo)
    doc = get_document(index_docs, todo["_id"])
    assert doc[i.field] == {"status": "done"}
    assert doc["class_label"] == "politics"

    refresh_index(index_docs)
    todos = list(get_todo(index_docs, i))
    assert {doc["_id"] for doc in todos} == {str(doc["_id"]) for doc in TEST_DOCUMENTS} - {todo["_id"]}
