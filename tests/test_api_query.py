from amcat4.elastic import refresh
from amcat4.query import query_documents
from tests.conftest import upload
from tests.tools import get_json, post_json, dictset

TEST_DOCUMENTS = [
    {'cat': 'a', 'subcat': 'x', 'i': 1, 'date': '2018-01-01', 'text': 'this is a text', },
    {'cat': 'a', 'subcat': 'x', 'i': 2, 'date': '2018-02-01', 'text': 'a test text', },
    {'cat': 'a', 'subcat': 'y', 'i': 11, 'date': '2020-01-01', 'text': 'and this is another test toto', 'title': 'bla'},
    {'cat': 'b', 'subcat': 'y', 'i': 31, 'date': '2018-01-01', 'text': 'Toto je testovací článek', 'title': 'more bla'},
]


def test_query_get(client, index_docs, user):
    """Can we run a simple query?"""

    def q(**query_string):
        return get_json(client, f"/index/{index_docs.name}/documents", user=user, params=query_string)['results']

    def qi(**query_string):
        return {int(doc['_id']) for doc in q(**query_string)}
    # TODO: check auth
    # Query strings
    assert qi(q="text") == {0, 1}
    assert qi(q="test*") == {1, 2, 3}

    # Filters
    assert qi(cat="a") == {0, 1, 2}
    assert qi(cat="b", q="test*") == {3}
    assert qi(date="2018-01-01") == {0, 3}
    assert qi(date__gte="2018-02-01") == {1, 2}
    assert qi(date__gt="2018-02-01") == {2}
    assert qi(date__gte="2018-02-01", date__lt="2020-01-01") == {1}

    # Can we request specific fields?
    all_fields = {"_id", "date", "text", "title", "cat", "subcat", "i"}
    assert set(q()[0].keys()) == all_fields
    assert set(q(fields="cat")[0].keys()) == {"_id", "cat"}
    assert set(q(fields="date,title")[0].keys()) == {"_id", "date", "title"}


def test_query_post(client, index_docs, user):

    def q(**body):
        return post_json(client, f"/index/{index_docs.name}/query", user=user, expected=200, json=body)['results']

    def qi(**query_string):
        return {int(doc['_id']) for doc in q(**query_string)}

    # Query strings
    assert qi(queries="text") == {0, 1}
    assert qi(queries="test*") == {1, 2, 3}
    assert qi(queries={}) == {0, 1, 2, 3}
    assert qi(queries={"test": "test*"}) == {1, 2, 3}

    # Filters
    assert qi(filters={'cat': 'a'}) == {0, 1, 2}
    assert qi(filters={'cat': 'b'}, queries="test*") == {3}
    assert qi(filters={'date': "2018-01-01"}) == {0, 3}
    assert qi(filters={'date': {'gte': "2018-02-01"}}) == {1, 2}
    assert qi(filters={'date': {'gt': "2018-02-01"}}) == {2}
    assert qi(filters={'date': {'gte': "2018-02-01", "lt": "2020-01-01"}}) == {1}
    assert qi(filters={'cat': {'values': ['a']}}) == {0, 1, 2}

    # Can we request specific fields?
    all_fields = {"_id", "date", "text", "title", "cat", "subcat", "i"}
    assert set(q()[0].keys()) == all_fields
    assert set(q(fields=["cat"])[0].keys()) == {"_id", "cat"}
    assert set(q(fields=["date", "title"])[0].keys()) == {"_id", "date", "title"}


def test_aggregate(client, index_docs, user):
    r = post_json(client, f"/index/{index_docs.name}/aggregate", user=user, expected=200,
                  json={'axes': [{'field': 'cat'}]})
    assert r['meta']['axes'][0]['field'] == 'cat'
    data = {d['cat']: d['n'] for d in r['data']}
    assert data == {"a": 3, "b": 1}

    # test calculated field
    r = post_json(client, f"/index/{index_docs.name}/aggregate", user=user, expected=200,
                  json={'axes': [{'field': 'subcat'}], 'aggregations': [{'field': "i", 'function': "avg"}]})
    assert dictset(r['data']) == dictset([{'avg_i': 1.5, 'n': 2, 'subcat': 'x'}, {'avg_i': 21.0, 'n': 2, 'subcat': 'y'}])
    assert r['meta']['aggregations'] == [{'field': "i", 'function': "avg", "type": "long", "name": "avg_i"}]

    # test filtered aggregate
    r = post_json(client, f"/index/{index_docs.name}/aggregate", user=user, expected=200,
                  json={'axes': [{'field': 'subcat'}], 'filters': {'cat': {'values': ['b']}}})
    data = {d['subcat']: d['n'] for d in r['data']}
    assert data == {"y": 1}

    # test filter+query aggregate
    r = post_json(client, f"/index/{index_docs.name}/aggregate", user=user, expected=200,
                  json={'axes': [{'field': 'subcat'}], 'queries': 'text', 'filters': {'cat': {'values': ['a']}}})
    data = {d['subcat']: d['n'] for d in r['data']}
    assert data == {"x": 2}


def test_multiple_index(client, index_docs, index, user):
    upload(index, [{"text": "also a text", "i": -1, 'cat': 'c'}], columns={'cat': 'keyword', 'i': 'long'})
    indices = f"{index.name},{index_docs.name}"
    assert len(get_json(client, f"/index/{indices}/documents", user=user)['results']) == 5
    assert len(post_json(client, f"/index/{indices}/query", user=user, expected=200)['results']) == 5
    r = post_json(client, f"/index/{indices}/aggregate", user=user, json={'axes': [{'field': 'cat'}]}, expected=200)
    assert dictset(r['data']) == dictset([{'cat': 'a', 'n': 3}, {'n': 1, 'cat': 'b'}, {'n': 1, 'cat': 'c'}])


def test_aggregate_datemappings(client, index_docs, user):
    r = post_json(client, f"/index/{index_docs.name}/aggregate", user=user, expected=200,
                  json={'axes': [{'field': 'date', 'interval': 'monthnr'}]})
    assert r['data'] == [{'date_monthnr': 1, 'n': 3}, {'date_monthnr': 2, 'n': 1}]
    assert [x['name'] for x in r['meta']['axes']] == ["date_monthnr"]
    r = post_json(client, f"/index/{index_docs.name}/aggregate", user=user, expected=200,
                  json={'axes': [{'field': 'date', 'interval': 'monthnr'}, {'field': 'date', 'interval': 'dayofmonth'}]})
    assert [x['name'] for x in r['meta']['axes']] == ["date_monthnr", "date_dayofmonth"]
    assert r['data'] == [{'date_monthnr': 1, 'date_dayofmonth': 1, 'n': 3},
                         {'date_monthnr': 2, 'date_dayofmonth': 1, 'n': 1}]


def test_query_tags(client, index_docs, user):
    def tags():
        return {doc['_id']: doc['tag']
                for doc in query_documents(index_docs.name, fields=["tag"]).data
                if doc.get('tag')}
    assert tags() == {}
    post_json(client, f"/index/{index_docs.name}/tags_update", user=user, expected=204,
              json=dict(action="add", field="tag", tag="x", filters={'cat': 'a'}))
    refresh(index_docs.name)
    assert tags() == {'0': ['x'], '1': ['x'], '2': ['x']}
    post_json(client, f"/index/{index_docs.name}/tags_update", user=user, expected=204,
              json=dict(action="remove", field="tag", tag="x", queries=["text"]))
    refresh(index_docs.name)
    assert tags() == {'2': ['x']}
    post_json(client, f"/index/{index_docs.name}/tags_update", user=user, expected=204,
              json=dict(action="add", field="tag", tag="y", ids=["1", "2"]))
    refresh(index_docs.name)
    assert tags() == {'1': ['y'], '2': ['x', 'y']}
