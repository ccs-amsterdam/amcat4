from amcat4.index import Role, refresh_index, set_role
from amcat4.models import CreateField, FieldSpec
from amcat4.query import query_documents
from tests.conftest import upload
from tests.tools import build_headers, check, post_json, dictset


def test_query_post(client, index_docs, user):
    def q(**body):
        return post_json(client, f"/index/{index_docs}/query", user=user, expected=200, json=body)["results"]

    def qi(**query_string):
        return {int(doc["_id"]) for doc in q(**query_string)}

    # Query strings
    assert qi(queries="text") == {0, 1}
    assert qi(queries="test*") == {1, 2, 3}
    assert qi(queries={}) == {0, 1, 2, 3}
    assert qi(queries={"test": "test*"}) == {1, 2, 3}

    # Filters
    assert qi(filters={"cat": "a"}) == {0, 1, 2}
    assert qi(filters={"cat": "b"}, queries="test*") == {3}
    assert qi(filters={"date": "2018-01-01"}) == {0, 3}
    assert qi(filters={"date": {"gte": "2018-02-01"}}) == {1, 2}
    assert qi(filters={"date": {"gt": "2018-02-01"}}) == {2}
    assert qi(filters={"date": {"gte": "2018-02-01", "lt": "2020-01-01"}}) == {1}
    assert qi(filters={"cat": {"values": ["a"]}}) == {0, 1, 2}

    # Can we request specific fields?
    all_fields = {"_id", "cat", "subcat", "i", "date", "text", "title"}
    assert set(q()[0].keys()) == all_fields
    assert set(q(fields=["cat"])[0].keys()) == {"_id", "cat"}
    assert set(q(fields=["date", "title"])[0].keys()) == {"_id", "date", "title"}


def test_aggregate(client, index_docs, user):
    r = post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={"axes": [{"field": "cat"}]},
    )
    assert r["meta"]["axes"][0]["field"] == "cat"
    data = {d["cat"]: d["n"] for d in r["data"]}
    assert data == {"a": 3, "b": 1}

    # test calculated field
    r = post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={
            "axes": [{"field": "subcat"}],
            "aggregations": [{"field": "i", "function": "avg"}],
        },
    )
    assert dictset(r["data"]) == dictset([{"avg_i": 1.5, "n": 2, "subcat": "x"}, {"avg_i": 21.0, "n": 2, "subcat": "y"}])
    assert r["meta"]["aggregations"] == [{"field": "i", "function": "avg", "type": "integer", "name": "avg_i"}]

    # test filtered aggregate
    r = post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={"axes": [{"field": "subcat"}], "filters": {"cat": {"values": ["b"]}}},
    )
    data = {d["subcat"]: d["n"] for d in r["data"]}
    assert data == {"y": 1}

    # test filter+query aggregate
    r = post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={
            "axes": [{"field": "subcat"}],
            "queries": "text",
            "filters": {"cat": {"values": ["a"]}},
        },
    )
    data = {d["subcat"]: d["n"] for d in r["data"]}
    assert data == {"x": 2}


def test_bare_aggregate(client, index_docs, user):
    r = post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={},
    )
    assert r["meta"]["axes"] == []
    assert r["data"] == [dict(n=4)]

    r = post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={"aggregations": [{"field": "i", "function": "avg"}]},
    )
    assert r["data"] == [dict(n=4, avg_i=11.25)]

    r = post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={"aggregations": [{"field": "i", "function": "min", "name": "mini"}]},
    )
    assert r["data"] == [dict(n=4, mini=1)]


def test_multiple_index(client, index_docs, index, user):
    set_role(index, user, Role.READER)
    upload(
        index,
        [{"text": "also a text", "i": -1, "cat": "c"}],
        fields={
            "text": CreateField(type="text"),
            "cat": CreateField(type="keyword"),
            "i": CreateField(type="integer"),
        },
    )
    indices = f"{index},{index_docs}"

    r = post_json(
        client,
        f"/index/{indices}/query",
        user=user,
        expected=200,
        json=dict(fields=["_id", "cat", "i"]),
    )
    assert len(r["results"]) == 5

    r = post_json(
        client,
        f"/index/{indices}/aggregate",
        user=user,
        json={"axes": [{"field": "cat"}], "fields": ["_id"]},
        expected=200,
    )
    assert dictset(r["data"]) == dictset([{"cat": "a", "n": 3}, {"n": 1, "cat": "b"}, {"n": 1, "cat": "c"}])


def test_aggregate_datemappings(client, index_docs, user):
    r = post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={"axes": [{"field": "date", "interval": "monthnr"}]},
    )
    assert r["data"] == [{"date_monthnr": 1, "n": 3}, {"date_monthnr": 2, "n": 1}]
    assert [x["name"] for x in r["meta"]["axes"]] == ["date_monthnr"]
    r = post_json(
        client,
        f"/index/{index_docs}/aggregate",
        user=user,
        expected=200,
        json={
            "axes": [
                {"field": "date", "interval": "monthnr"},
                {"field": "date", "interval": "dayofmonth"},
            ]
        },
    )
    assert [x["name"] for x in r["meta"]["axes"]] == ["date_monthnr", "date_dayofmonth"]
    assert r["data"] == [
        {"date_monthnr": 1, "date_dayofmonth": 1, "n": 3},
        {"date_monthnr": 2, "date_dayofmonth": 1, "n": 1},
    ]


def test_query_tags(client, index_docs, user):
    def tags():
        result = query_documents(index_docs, fields=[FieldSpec(name="tag")])
        return {doc["_id"]: doc["tag"] for doc in (result.data if result else []) if doc.get("tag")}

    check(client.post(f"/index/{index_docs}/tags_update"), 401)
    check(client.post(f"/index/{index_docs}/tags_update", headers=build_headers(user=user)), 401)

    set_role(index_docs, user, Role.WRITER)

    assert tags() == {}
    res = post_json(
        client,
        f"/index/{index_docs}/tags_update",
        user=user,
        expected=200,
        json=dict(action="add", field="tag", tag="x", filters={"cat": "a"}),
    )
    assert res["updated"] == 3
    # should refresh before returning
    # refresh_index(index_docs)
    assert tags() == {"0": ["x"], "1": ["x"], "2": ["x"]}
    res = post_json(
        client,
        f"/index/{index_docs}/tags_update",
        user=user,
        expected=200,
        json=dict(action="remove", field="tag", tag="x", queries=["text"]),
    )
    assert res["updated"] == 2
    assert tags() == {"2": ["x"]}
    res = post_json(
        client,
        f"/index/{index_docs}/tags_update",
        user=user,
        expected=200,
        json=dict(action="add", field="tag", tag="y", ids=["1", "2"]),
    )
    assert res["updated"] == 2
    assert tags() == {"1": ["y"], "2": ["x", "y"]}
