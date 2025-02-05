import functools
from typing import Set, Optional

from amcat4 import query
from amcat4.models import FieldSpec, FilterSpec, FilterValue, SnippetParams
from amcat4.api.query import _standardize_queries, _standardize_filters
from tests.conftest import upload


def query_ids(
    index: str,
    q: Optional[str | list[str]] = None,
    filters: dict[str, FilterValue | list[FilterValue] | FilterSpec] | None = None,
    **kwargs,
) -> Set[int]:
    if q is not None:
        kwargs["queries"] = _standardize_queries(q)
    if filters is not None:
        kwargs["filters"] = _standardize_filters(filters)

    res = query.query_documents(index, **kwargs)
    if res is None:
        return set()
    return {int(h["_id"]) for h in res.data}


def test_query(index_docs):
    q = functools.partial(query_ids, index_docs)

    assert q("test") == {1, 2}
    assert q("test*") == {1, 2, 3}
    assert q('"a text"') == {0}

    assert q(["this", "toto"]) == {0, 2, 3}

    assert q(filters={"title": ["title"]}) == {0, 1}
    assert q("this", filters={"title": ["title"]}) == {0}
    assert q("this") == {0, 2}


def test_snippet(index_docs):
    docs = query.query_documents(index_docs, fields=[FieldSpec(name="text", snippet=SnippetParams(nomatch_chars=5))])
    assert docs is not None
    assert docs.data[0]["text"] == "this is"

    docs = query.query_documents(
        index_docs, queries={"1": "a"}, fields=[FieldSpec(name="text", snippet=SnippetParams(max_matches=1, match_chars=1))]
    )
    assert docs is not None
    assert docs.data[0]["text"] == "a"


def test_range_query(index_docs):
    q = functools.partial(query_ids, index_docs)
    assert q(filters={"date": FilterSpec(gt="2018-02-01")}) == {2}
    assert q(filters={"date": FilterSpec(gte="2018-02-01")}) == {1, 2}
    assert q(filters={"date": FilterSpec(gte="2018-02-01", lt="2020-01-01")}) == {1}
    assert q("title", filters={"date": FilterSpec(gt="2018-01-01")}) == {1}


def test_fields(index_docs):
    res = query.query_documents(index_docs, queries={"1": "test"}, fields=[FieldSpec(name="cat"), FieldSpec(name="title")])
    assert res is not None
    assert set(res.data[0].keys()) == {"cat", "title", "_id"}


def test_highlight(index):
    words = "The error of regarding functional notions is not quite equivalent to"
    text = f"{words} a test document. {words} other text documents. {words} you!"
    upload(index, [dict(title="Een test titel", text=text)], fields={"title": "text", "text": "text"})
    res = query.query_documents(
        index, fields=[FieldSpec(name="title"), FieldSpec(name="text")], queries={"1": "te*"}, highlight=True
    )
    assert res is not None
    doc = res.data[0]
    assert doc["title"] == "Een <em>test</em> titel"
    assert doc["text"] == f"{words} a <em>test</em> document. {words} other <em>text</em> documents. {words} you!"

    res = query.query_documents(
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


def test_query_multiple_index(index_docs, index):
    upload(index, [{"text": "also a text", "i": -1}], fields={"i": "integer", "text": "text"})
    docs = query.query_documents([index_docs, index])
    assert docs is not None
    assert len(docs.data) == 5


# TODO: Do we want to support this? What are the options?
#       If so, need to add it to FilterSpec
# def test_query_filter_mapping(index_docs):
#     q = functools.partial(query_ids, index_docs)
#     assert q(filters={"date": {"monthnr": "2"}}) == {1}
#     assert q(filters={"date": {"dayofweek": "Monday"}}) == {0, 3}
