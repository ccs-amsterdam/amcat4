import functools
from time import sleep
from typing import Optional, Set

import pytest
from pytest import raises

from amcat4.api.index_query import _standardize_filters, _standardize_queries
from amcat4.models import FieldSpec, FilterSpec, FilterValue, ProjectSettings, SnippetParams
from amcat4.projects.index import create_project_index, delete_project_index, refresh_index
from amcat4.projects.query import get_task_status, query_documents, reindex
from amcat4.systemdata.fields import list_fields
from tests.conftest import upload


async def query_ids(
    index: str,
    q: Optional[str | list[str]] = None,
    filters: dict[str, FilterValue | list[FilterValue] | FilterSpec] | None = None,
    **kwargs,
) -> Set[int]:
    if q is not None:
        kwargs["queries"] = _standardize_queries(q)
    if filters is not None:
        kwargs["filters"] = _standardize_filters(filters)

    res = await query_documents(index, **kwargs)
    if res is None:
        return set()
    return {int(h["_id"]) for h in res.data}


@pytest.mark.anyio
async def test_query(index_docs):
    q = functools.partial(query_ids, index_docs)

    assert await q("test") == {1, 2}
    assert await q("test*") == {1, 2, 3}
    assert await q('"a text"') == {0}

    assert await q(["this", "toto"]) == {0, 2, 3}

    assert await q(filters={"title": ["title"]}) == {0, 1}
    assert await q("this", filters={"title": ["title"]}) == {0}
    assert await q("this") == {0, 2}


@pytest.mark.anyio
async def test_snippet(index_docs):
    docs = await query_documents(index_docs, fields=[FieldSpec(name="text", snippet=SnippetParams(nomatch_chars=5))])
    assert docs is not None
    assert docs.data[0]["text"] == "this is"

    docs = await query_documents(
        index_docs, queries={"1": "a"}, fields=[FieldSpec(name="text", snippet=SnippetParams(max_matches=1, match_chars=1))]
    )
    assert docs is not None
    assert docs.data[0]["text"] == "a"


@pytest.mark.anyio
async def test_range_query(index_docs):
    q = functools.partial(query_ids, index_docs)
    assert await q(filters={"date": FilterSpec(gt="2018-02-01")}) == {2}
    assert await q(filters={"date": FilterSpec(gte="2018-02-01")}) == {1, 2}
    assert await q(filters={"date": FilterSpec(gte="2018-02-01", lt="2020-01-01")}) == {1}
    assert await q("title", filters={"date": FilterSpec(gt="2018-01-01")}) == {1}


@pytest.mark.anyio
async def test_fields(index_docs):
    res = await query_documents(index_docs, queries={"1": "test"}, fields=[FieldSpec(name="cat"), FieldSpec(name="title")])
    assert res is not None
    assert set(res.data[0].keys()) == {"cat", "title", "_id"}


@pytest.mark.anyio
async def test_highlight(index):
    words = "The error of regarding functional notions is not quite equivalent to"
    text = f"{words} a test document. {words} other text documents. {words} you!"
    await upload(index, [dict(title="Een test titel", text=text)], fields={"title": "text", "text": "text"})
    res = await query_documents(
        index, fields=[FieldSpec(name="title"), FieldSpec(name="text")], queries={"1": "te*"}, highlight=True
    )
    assert res is not None
    doc = res.data[0]
    assert doc["title"] == "Een <em>test</em> titel"
    assert doc["text"] == f"{words} a <em>test</em> document. {words} other <em>text</em> documents. {words} you!"

    res = await query_documents(
        index,
        queries={"1": "te*"},
        fields=[
            FieldSpec(name="title", snippet=SnippetParams(max_matches=3, match_chars=50)),
            FieldSpec(name="text", snippet=SnippetParams(max_matches=3, match_chars=50)),
        ],
        highlight=True,
    )
    assert res is not None
    doc = res.data[0]
    assert doc["title"] == "Een <em>test</em> titel"
    assert " a <em>test</em>" in doc["text"]
    assert " ... " in doc["text"]


@pytest.mark.anyio
async def test_query_multiple_index(index_docs, index):
    await upload(index, [{"text": "also a text", "i": -1}], fields={"i": "integer", "text": "text"})
    docs = await query_documents([index_docs, index])
    assert docs is not None
    assert len(docs.data) == 5


# TODO: Do we want to support this? What are the options?
#       If so, need to add it to FilterSpec
@pytest.mark.anyio
async def test_query_filter_mapping(index_docs):
    q = functools.partial(query_ids, index_docs)
    assert await q(filters={"date": FilterSpec(monthnr=2)}) == {1}
    assert await q(filters={"date": FilterSpec(dayofweek="Monday")}) == {0, 3}


@pytest.mark.anyio
async def test_reindex(index_docs, index_name):
    # Re-indexing should error if destination does not exist
    with raises(Exception):
        await reindex(source_index=index_docs, destination_index=index_name)
    project = ProjectSettings(id=index_name)
    await create_project_index(project)
    task = await reindex(source_index=index_docs, destination_index=index_name)
    while True:
        status = await get_task_status(task["task"])
        if status["completed"]:
            break
        sleep(0.1)
    await refresh_index(index_name)
    assert await query_ids(index_docs) == await query_ids(index_name)
    assert await list_fields(index_docs) == await list_fields(index_name)

    await delete_project_index(index_name)
    await create_project_index(project)
    await reindex(
        source_index=index_docs,
        destination_index=index_name,
        filters={"cat": FilterSpec(values=["b"])},
        wait_for_completion=True,
    )

    await refresh_index(index_name)
    assert await query_ids(index_name) == {3}
