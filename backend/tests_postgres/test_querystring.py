import pytest

from amcat4.postgres.fields import FieldInfo, FieldSet, QueryError
from amcat4.postgres.querystring import Bool, Phrase, Range, Term, parse_query, query_string_to_json

FIELDS = {
    "title": FieldInfo(1, "title", "text"),
    "text": FieldInfo(2, "text", "text"),
    "source": FieldInfo(3, "source", "keyword"),
    "n": FieldInfo(4, "n", "integer"),
    "date": FieldInfo(5, "date", "date"),
    "secret": FieldInfo(6, "secret", "text"),
}


def fieldset(queryable=None):
    return FieldSet({1: FIELDS}, queryable=queryable)


def test_parse_terms_and_operators():
    assert parse_query("fox") == Term(None, "fox")
    assert parse_query("a AND b") == Bool([("must", Term(None, "a")), ("must", Term(None, "b"))])
    assert parse_query("a OR b") == Bool([("should", Term(None, "a")), ("should", Term(None, "b"))])
    assert parse_query("a -b") == Bool([("should", Term(None, "a")), ("must_not", Term(None, "b"))])
    assert parse_query("a AND NOT b") == Bool([("must", Term(None, "a")), ("must_not", Term(None, "b"))])
    assert parse_query("a b", default_operator="AND") == Bool([("must", Term(None, "a")), ("must", Term(None, "b"))])
    # AND binds stronger than juxtaposition
    q = parse_query("a b AND c")
    assert isinstance(q, Bool) and q.clauses[0] == ("should", Term(None, "a"))


def test_parse_fields_phrases_ranges():
    assert parse_query("title:fox") == Term("title", "fox")
    assert parse_query('"quick fox"~2') == Phrase(None, "quick fox", slop=2)
    assert parse_query("title:(a OR b)") == Bool([("should", Term("title", "a")), ("should", Term("title", "b"))])
    assert parse_query("n:[1 TO 5}") == Range("n", "1", "5", True, False)
    assert parse_query("n:>=3") == Range("n", "3", None, True, True)
    assert parse_query("date:[2020-01-01 TO *]") == Range("date", "2020-01-01", None)
    assert parse_query("foxx~1^2") == Term(None, "foxx", fuzzy=1, boost=2.0)
    assert parse_query("e-mail") == Term(None, "e-mail")


@pytest.mark.parametrize("q", ["(a", "a)", "AND", "title:", '"unclosed'])
def test_parse_errors(q):
    with pytest.raises(QueryError):
        parse_query(q)


def test_compile_default_fields_and_visibility():
    # no field: search all queryable text fields
    q = query_string_to_json("fox", fieldset())
    assert {c["match"]["field"] for c in q["boolean"]["should"]} == {"text_data.f1", "text_data.f2", "text_data.f6"}
    q = query_string_to_json("fox", fieldset(queryable={"title", "source"}))
    assert q == {"match": {"field": "text_data.f1", "value": "fox"}}
    with pytest.raises(QueryError):
        query_string_to_json("secret:fox", fieldset(queryable={"title"}))
    with pytest.raises(QueryError):
        query_string_to_json("nonexisting:fox", fieldset())


def test_compile_leaves():
    fs = fieldset()
    assert query_string_to_json("title:immigr*", fs) == {"phrase_prefix": {"field": "text_data.f1", "phrases": ["immigr"]}}
    assert query_string_to_json('title:"Quick Fox"~1', fs) == {
        "phrase": {"field": "text_data.f1", "phrases": ["quick", "fox"], "slop": 1}
    }
    assert query_string_to_json('source:"New York"', fs) == {"term": {"field": "meta_data.f3", "value": "New York"}}
    assert query_string_to_json("n:42", fs) == {"term": {"field": "meta_data.f4", "value": 42}}
    r = query_string_to_json("n:>5", fs)["range"]
    assert r["lower_bound"] == {"excluded": 5} and r["upper_bound"] is None
    r = query_string_to_json("date:2024-01-01", fs)["range"]
    assert r["lower_bound"] == {"included": "2024-01-01T00:00:00.000000Z"}
    assert r["upper_bound"] == {"included": "2024-01-01T23:59:59.999999Z"}
    with pytest.raises(QueryError):
        query_string_to_json("title:a*b", fs)
    with pytest.raises(QueryError):
        query_string_to_json("title:[a TO b]", fs)
    assert query_string_to_json("-title:fox", fs) == {
        "boolean": {"must": [{"all": None}], "must_not": [{"match": {"field": "text_data.f1", "value": "fox"}}]}
    }


def test_compile_multi_project():
    other = {"title": FieldInfo(11, "title", "text")}
    fs = FieldSet({1: FIELDS, 2: other})
    q = query_string_to_json("title:fox", fs)
    assert {c["match"]["field"] for c in q["boolean"]["should"]} == {"text_data.f1", "text_data.f11"}
