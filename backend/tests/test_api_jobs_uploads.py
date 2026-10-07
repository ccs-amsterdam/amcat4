"""API tests for copy jobs, upload operations, field management and importing (old) project exports"""

import json

import pytest

from amcat4.models import ProjectSettings, Roles
from amcat4.projects.index import create_project_index
from amcat4.projects.jobs import run_pending_jobs
from amcat4.systemdata.roles import create_project_role
from tests.tools import adelete, auth_cookie, get_json, post_json


@pytest.mark.anyio
async def test_copy_job(client, index_docs, index_name, user, writer2):
    await create_project_index(ProjectSettings(id=index_name))
    await create_project_role(user, index_docs, Roles.READER)
    body = {"destination": index_name, "filters": {"cat": {"values": ["a"]}}}
    # user needs WRITER on the destination
    await post_json(client, f"/index/{index_docs}/copy", user=user, json=body, expected=403)
    await create_project_role(user, index_name, Roles.WRITER)
    job = await post_json(client, f"/index/{index_docs}/copy", user=user, json=body, expected=202)
    assert job["status"] == "pending" and job["type"] == "copy"
    # Other users cannot see the job
    await get_json(client, f"/jobs/{job['id']}", user=writer2, expected=403)
    await run_pending_jobs()
    job = await get_json(client, f"/jobs/{job['id']}", user=user)
    assert job["status"] == "done" and job["result"] == {"copied": 3}
    assert [j["id"] for j in await get_json(client, "/jobs", user=user)] == [job["id"]]
    assert [j["id"] for j in await get_json(client, f"/jobs?project={index_name}", user=user)] == [job["id"]]
    # Cancelling a finished job does nothing
    await adelete(client, f"/jobs/{job['id']}", user=user)
    assert (await get_json(client, f"/jobs/{job['id']}", user=user))["status"] == "done"


@pytest.mark.anyio
async def test_cancel_job(client, index_docs, index_name, admin):
    await create_project_index(ProjectSettings(id=index_name))
    job = await post_json(client, f"/index/{index_docs}/copy", user=admin, json={"destination": index_name}, expected=202)
    await adelete(client, f"/jobs/{job['id']}", user=admin)
    assert await run_pending_jobs() == 0
    assert (await get_json(client, f"/jobs/{job['id']}", user=admin))["status"] == "cancelled"


@pytest.mark.anyio
async def test_upload_operations(client, index, admin):
    url = f"/index/{index}/documents"
    fields = {"url": {"type": "keyword", "unique": True}, "title": "text", "n": "integer"}
    docs = [{"url": "a", "title": "A", "n": 1}, {"url": "b", "title": "B", "n": 2}]
    r = await post_json(client, url, user=admin, json={"documents": docs, "fields": fields})
    assert r == {"created": 2, "updated": 0}
    # create fails if any document exists, and saves nothing
    body = {"documents": [{"url": "c", "title": "C"}, {"url": "a", "title": "A2"}], "operation": "create"}
    r = await post_json(client, url, user=admin, json=body, expected=409)
    assert "already exist" in r["detail"]
    # update fails if any document does not exist
    body = {"documents": [{"url": "c", "n": 3}], "operation": "update"}
    await post_json(client, url, user=admin, json=body, expected=409)
    # upsert keeps other fields
    body = {"documents": [{"url": "a", "n": 10}, {"url": "c", "n": 3}], "operation": "upsert"}
    assert await post_json(client, url, user=admin, json=body) == {"created": 1, "updated": 1}
    r = await post_json(client, f"/index/{index}/query", user=admin, json={"fields": ["url", "title", "n"]}, expected=200)
    assert sorted((d["url"], d.get("title"), d["n"]) for d in r["results"]) == [("a", "A", 10), ("b", "B", 2), ("c", None, 3)]
    # invalid values
    body = {"documents": [{"url": "d", "n": "many"}]}
    await post_json(client, url, user=admin, json=body, expected=422)


@pytest.mark.anyio
async def test_rename_and_convert_field(client, index_docs, admin):
    r = await client.put(f"/index/{index_docs}/fields", cookies=auth_cookie(admin), json={"cat": {"name": "category"}})
    assert r.status_code == 204, r.text
    r = await client.put(f"/index/{index_docs}/fields", cookies=auth_cookie(admin), json={"i": {"type": "keyword"}})
    assert r.status_code == 204, r.text
    fields = await get_json(client, f"/index/{index_docs}/fields", user=admin)
    assert "category" in fields and "cat" not in fields and fields["i"]["type"] == "keyword"
    assert await get_json(client, f"/index/{index_docs}/fields/category/values", user=admin) == ["a", "b"]
    assert await get_json(client, f"/index/{index_docs}/fields/category/values?size=1", user=admin) == ["a"]
    stats = await get_json(client, f"/index/{index_docs}/fields/date/stats", user=admin)
    assert stats["count"] == 4 and stats["min"].startswith("2018-01-01")


@pytest.mark.anyio
async def test_aggregate_order_and_limit(client, index_docs, admin):
    url = f"/index/{index_docs}/aggregate"
    r = await post_json(client, url, user=admin, json={"axes": [{"field": "cat"}], "order": "count"}, expected=200)
    assert [d["cat"] for d in r["data"]] == ["a", "b"] and not r["meta"]["truncated"]
    r = await post_json(client, url, user=admin, json={"axes": [{"field": "cat"}], "order": "count", "limit": 1}, expected=200)
    assert [d["cat"] for d in r["data"]] == ["a"] and r["meta"]["truncated"]


@pytest.mark.anyio
async def test_query_errors(client, index_docs, admin):
    r = await client.post(f"/index/{index_docs}/query", cookies=auth_cookie(admin), json={"queries": {"bad": "te*xt"}})
    assert r.status_code == 400
    assert "bad" in r.text and "Wildcards" in r.text


@pytest.mark.anyio
async def test_import_legacy_export(client, index_name, admin):
    """Exports from elasticsearch based AmCAT servers have elastic types, identifiers and snippets in characters"""
    lines = [
        {"_type": "settings", "id": index_name, "name": "Old project"},
        {"_type": "field", "name": "url", "type": "keyword", "elastic_type": "keyword", "identifier": True},
        {
            "_type": "field",
            "name": "text",
            "type": "text",
            "elastic_type": "text",
            "identifier": False,
            "metareader": {"access": "snippet", "max_snippet": {"nomatch_chars": 120, "max_matches": 2, "match_chars": 60}},
        },
        {"_type": "user_role", "email": "someone@example.com", "role": "READER"},
        {"_type": "document", "_id": "oldid1", "url": "http://a", "text": "Some text"},
        {"_type": "document", "_id": "oldid2", "url": "http://b", "text": "More text"},
    ]
    content = "\n".join(json.dumps(line) for line in lines).encode()
    r = await client.post(
        "/index/import", cookies=auth_cookie(admin), files={"file": ("export.ndjson", content, "application/x-ndjson")}
    )
    assert r.status_code == 201, r.text
    assert r.json()["n_documents"] == 2
    fields = await get_json(client, f"/index/{index_name}/fields", user=admin)
    assert fields["url"]["unique"] is True and "elastic_type" not in fields["url"]
    assert fields["text"]["metareader"]["max_snippet"] == {"nomatch_words": 20, "max_matches": 2, "words_per_match": 10}
    doc = await get_json(client, f"/index/{index_name}/documents/oldid1", user=admin)
    assert doc["url"] == "http://a"
