from tests.conftest import upload
from tests.tools import get_json, post_json, dictset


def test_query_get(client, index_docs, user):
    """Can we run a simple query?"""

    def q(**query_string):
        return get_json(client, f"/index/{index_docs.name}/documents", user=user, query_string=query_string)['results']

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

    # Filters
    assert qi(filters={'cat': 'a'}) == {0, 1, 2}
    assert qi(filters={'cat': 'b'}, queries="test*") == {3}
    assert qi(filters={'date': "2018-01-01"}) == {0, 3}
    assert qi(filters={'date': {'gte': "2018-02-01"}}) == {1, 2}
    assert qi(filters={'date': {'gt': "2018-02-01"}}) == {2}
    assert qi(filters={'date': {'gte': "2018-02-01", "lt": "2020-01-01"}}) == {1}

    # Can we request specific fields?
    all_fields = {"_id", "date", "text", "title", "cat", "subcat", "i"}
    assert set(q()[0].keys()) == all_fields
    assert set(q(fields="cat")[0].keys()) == {"_id", "cat"}
    assert set(q(fields=["date", "title"])[0].keys()) == {"_id", "date", "title"}


def test_aggregate(client, index_docs, user):
    r = post_json(client, f"/index/{index_docs.name}/aggregate", user=user, expected=200,
                  json={'axes': [{'field': 'cat'}]})
    assert r['meta']['axes'][0]['field'] == 'cat'
    data = {d['cat']: d['n'] for d in r['data']}
    assert data == {"a": 3, "b": 1}

    r = post_json(client, f"/index/{index_docs.name}/aggregate", user=user, expected=200,
                  json={'axes': [{'field': 'subcat'}], 'aggregations': [{'field': "i", 'function': "avg"}]})
    assert dictset(r['data']) == dictset([{'avg_i': 1.5, 'n': 2, 'subcat': 'x'}, {'avg_i': 21.0, 'n': 2, 'subcat': 'y'}])
    assert r['meta']['aggregations'] == [{'field': "i", 'function': "avg", "type": "long", "name": "avg_i"}]


def test_multiple_index(client, index_docs, index, user):
    upload(index, [{"text": "also a text", "i": -1}])
    indices = f"{index.name},{index_docs.name}"
    assert len(get_json(client, f"/index/{indices}/documents", user=user)['results']) == 5
    assert len(post_json(client, f"/index/{indices}/query", user=user, expected=200)['results']) == 5
