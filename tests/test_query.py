import functools
import re
from typing import Set, Optional

from amcat4 import query
from amcat4.index import Index
from tests.conftest import upload


def query_ids(index: Index, q: Optional[str] = None, **kwargs) -> Set[int]:
    if q is not None:
        kwargs['queries'] = [q]
    res = query.query_documents(index.name, **kwargs)
    return {int(h['_id']) for h in res.data}


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
    res = query.query_documents(index_docs.name, queries=["test"], fields=["cat", "title"])
    assert set(res.data[0].keys()) == {"cat", "title", "_id"}


def test_highlight(index):
    words = "The error of regarding functional notions is not quite equivalent to"
    text = f"{words} a test document. {words} other text documents. {words} you!"
    upload(index, [dict(title="Een test titel", text=text)])
    res = query.query_documents(index.name, queries=["te*"], highlight=True)
    doc = res.data[0]
    assert doc['title'] == "Een <em>test</em> titel"
    assert doc['text'] == f"{words} a <em>test</em> document. {words} other <em>text</em> documents. {words} you!"

    doc = query.query_documents(index.name, queries=["te*"], highlight={"number_of_fragments": 1}).data[0]
    assert doc['title'] == "Een <em>test</em> titel"
    assert " a <em>test</em>" in doc['text']
    assert "..." not in doc['text']

    doc = query.query_documents(index.name, queries=["te*"], highlight={"number_of_fragments": 2}).data[0]
    assert re.search(r" a <em>test</em>[^<]*...[^<]*other <em>text</em> documents", doc['text'])


def test_query_multiple_index(index_docs, index):
    upload(index, [{"text": "also a text", "i": -1}])
    assert len(query.query_documents([index_docs.name, index.name]).data) == 5
