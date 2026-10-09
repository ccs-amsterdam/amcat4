import pytest

from amcat4.postgres.fields import FieldInfo, FieldSet, QueryError
from amcat4.postgres.querystring import (
    Bool,
    Phrase,
    Range,
    Term,
    highlight_patterns,
    match_positions,
    parse_query,
    query_string_to_json,
)

# The (autouse) setup fixture in conftest is async, so these tests need to run under anyio as well
pytestmark = pytest.mark.anyio

FIELDS = {
    "title": FieldInfo(1, "title", "text"),
    "text": FieldInfo(2, "text", "text"),
    "source": FieldInfo(3, "source", "keyword"),
    "n": FieldInfo(4, "n", "integer"),
    "date": FieldInfo(5, "date", "date"),
    "secret": FieldInfo(6, "secret", "text"),
    "location": FieldInfo(7, "location", "geo_point"),
}


def fieldset(queryable=None):
    return FieldSet({1: FIELDS}, queryable=queryable)


async def test_parse_terms_and_operators():
    assert parse_query("fox") == Term(None, "fox")
    assert parse_query("a AND b") == Bool([("must", Term(None, "a")), ("must", Term(None, "b"))])
    assert parse_query("a OR b") == Bool([("should", Term(None, "a")), ("should", Term(None, "b"))])
    assert parse_query("a -b") == Bool([("should", Term(None, "a")), ("must_not", Term(None, "b"))])
    assert parse_query("a AND NOT b") == Bool([("must", Term(None, "a")), ("must_not", Term(None, "b"))])
    assert parse_query("a b", default_operator="AND") == Bool([("must", Term(None, "a")), ("must", Term(None, "b"))])
    # AND binds stronger than juxtaposition
    q = parse_query("a b AND c")
    assert isinstance(q, Bool) and q.clauses[0] == ("should", Term(None, "a"))


async def test_parse_fields_phrases_ranges():
    assert parse_query("title:fox") == Term("title", "fox")
    assert parse_query('"quick fox"~2') == Phrase(None, "quick fox", slop=2)
    assert parse_query("title:(a OR b)") == Bool([("should", Term("title", "a")), ("should", Term("title", "b"))])
    assert parse_query("n:[1 TO 5}") == Range("n", "1", "5", True, False)
    assert parse_query("n:>=3") == Range("n", "3", None, True, True)
    assert parse_query("date:[2020-01-01 TO *]") == Range("date", "2020-01-01", None)
    assert parse_query("foxx~1^2") == Term(None, "foxx", fuzzy=1, boost=2.0)
    assert parse_query("e-mail") == Term(None, "e-mail")


@pytest.mark.parametrize("q", ["(a", "a)", "AND", "title:", '"unclosed'])
async def test_parse_errors(q):
    with pytest.raises(QueryError):
        parse_query(q)


async def test_compile_default_fields_and_visibility():
    # no field: search all queryable text fields
    q = query_string_to_json("fox", fieldset())
    assert {c["match"]["field"] for c in q["boolean"]["should"]} == {"text_fields.f1", "text_fields.f2", "text_fields.f6"}
    q = query_string_to_json("fox", fieldset(queryable={"title", "source"}))
    assert q == {"match": {"field": "text_fields.f1", "value": "fox"}}
    with pytest.raises(QueryError):
        query_string_to_json("secret:fox", fieldset(queryable={"title"}))
    with pytest.raises(QueryError):
        query_string_to_json("nonexisting:fox", fieldset())


async def test_compile_leaves():
    fs = fieldset()
    assert query_string_to_json("title:immigr*", fs) == {"phrase_prefix": {"field": "text_fields.f1", "phrases": ["immigr"]}}
    assert query_string_to_json('title:"Quick Fox"~1', fs) == {
        "phrase": {"field": "text_fields.f1", "phrases": ["quick", "fox"], "slop": 1}
    }
    assert query_string_to_json('source:"New York"', fs) == {"term": {"field": "exact_fields.f3", "value": "New York"}}
    assert query_string_to_json("n:42", fs) == {"term": {"field": "exact_fields.f4", "value": 42}}
    r = query_string_to_json("n:>5", fs)["range"]
    assert r["lower_bound"] == {"excluded": 5} and r["upper_bound"] is None
    r = query_string_to_json("date:2024-01-01", fs)["range"]
    assert r["lower_bound"] == {"included": "2024-01-01T00:00:00.000000Z"}
    assert r["upper_bound"] == {"included": "2024-01-01T23:59:59.999999Z"}
    r = query_string_to_json("location.lat:>50", fs)["range"]
    assert r["field"] == "exact_fields.f7.lat" and r["lower_bound"] == {"excluded": 50.0}
    with pytest.raises(QueryError):
        query_string_to_json("title:a*b", fs)
    with pytest.raises(QueryError):
        query_string_to_json("title:[a TO b]", fs)
    assert query_string_to_json("-title:fox", fs) == {
        "boolean": {"must": [{"all": None}], "must_not": [{"match": {"field": "text_fields.f1", "value": "fox"}}]}
    }


async def test_compile_multi_project():
    other = {"title": FieldInfo(11, "title", "text")}
    fs = FieldSet({1: FIELDS, 2: other})
    q = query_string_to_json("title:fox", fs)
    assert {c["match"]["field"] for c in q["boolean"]["should"]} == {"text_fields.f1", "text_fields.f11"}


async def test_highlight_patterns():
    q = parse_query('te* OR "quick fox" -nope title:x')
    patterns = highlight_patterns(q, "text", default_field=True)
    assert match_positions("A test text. Quick, fox! nope", patterns) == [[2, 6], [7, 11], [13, 23]]
    assert highlight_patterns(q, "text", default_field=False) == []


async def test_proximity_highlight():
    q = parse_query('"house representatives"~2')
    patterns = highlight_patterns(q, "text", default_field=True)
    # reversed order is allowed (distance 2 from the expected position), but 'House x y z representatives' is too far
    text = "The House of Representatives. Representatives house. House x y z representatives"
    assert match_positions(text, patterns) == [[4, 9], [13, 28], [30, 45], [46, 51]]
    patterns = highlight_patterns(parse_query('"house representatives"~1'), "text", default_field=True)
    assert match_positions(text, patterns) == [[4, 9], [13, 28]]


async def test_phrase_wildcards():
    fs = FieldSet({1: FIELDS})
    assert query_string_to_json('title:"quick fo*"', fs) == {
        "phrase_prefix": {"field": "text_fields.f1", "phrases": ["quick", "fo"]}
    }
    with pytest.raises(QueryError, match="proximity"):
        query_string_to_json('title:"quick fo*"~2', fs)
    with pytest.raises(QueryError, match="end of a phrase"):
        query_string_to_json('title:"qu* fox"', fs)
