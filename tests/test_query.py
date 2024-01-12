import functools
import re
from typing import Set, Optional

from amcat4 import query
from tests.conftest import upload


def query_ids(index: str, q: Optional[str] = None, **kwargs) -> Set[int]:
    if q is not None:
        kwargs["queries"] = [q]
    res = query.query_documents(index, **kwargs)
    if res is None:
        return set()
    return {int(h["_id"]) for h in res.data}


def test_query(index_docs):
    q = functools.partial(query_ids, index_docs)
    assert q("test") == {1, 2}
    assert q("test*") == {1, 2, 3}
    assert q('"a text"') == {0}

    assert q(queries=["this", "toto"]) == {0, 2, 3}

    assert q(filters={"title": {"value": "title"}}) == {0, 1}
    assert q("this", filters={"title": {"value": "title"}}) == {0}
    assert q("this") == {0, 2}


def test_range_query(index_docs):
    q = functools.partial(query_ids, index_docs)
    assert q(filters={"date": {"gt": "2018-02-01"}}) == {2}
    assert q(filters={"date": {"gte": "2018-02-01"}}) == {1, 2}
    assert q(filters={"date": {"gte": "2018-02-01", "lt": "2020-01-01"}}) == {1}
    assert q("title", filters={"date": {"gt": "2018-01-01"}}) == {1}


def test_fields(index_docs):
    res = query.query_documents(index_docs, queries=["test"], fields=["cat", "title"])
    assert res is not None
    assert set(res.data[0].keys()) == {"cat", "title", "_id"}


def test_highlight(index):
    words = "The error of regarding functional notions is not quite equivalent to"
    text = f"{words} a test document. {words} other text documents. {words} you!"
    upload(index, [dict(title="Een test titel", text=text)])
    res = query.query_documents(index, fields=["title", "text"], queries=["te*"], highlight=True)
    assert res is not None
    doc = res.data[0]
    assert doc["title"] == "Een <em>test</em> titel"
    assert doc["text"] == f"{words} a <em>test</em> document. {words} other <em>text</em> documents. {words} you!"

    # snippets can also have highlights
    doc = query.query_documents(index, queries=["te*"], fields=["title"], snippets=["text"], highlight=True).data[0]
    assert doc["title"] == "Een <em>test</em> titel"
    assert " a <em>test</em>" in doc["text"]
    assert " ... " in doc["text"]


def test_query_multiple_index(index_docs, index):
    upload(index, [{"text": "also a text", "i": -1}])
    docs = query.query_documents([index_docs, index])
    assert docs is not None
    assert len(docs.data) == 5


def test_query_filter_mapping(index_docs):
    q = functools.partial(query_ids, index_docs)
    assert q(filters={"date": {"monthnr": "2"}}) == {1}
    assert q(filters={"date": {"dayofweek": "Monday"}}) == {0, 3}
