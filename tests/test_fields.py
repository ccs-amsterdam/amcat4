import pytest

from amcat4.fields import field_values, get_fields, set_fields
from amcat4.index import refresh_index, upload_documents
from amcat4.models import FieldValue, PartialField
from tests.test_elastic import create_fields
from tests.tools import refresh


def test_fields(index):
    """Can we get the fields from an index"""
    create_fields(index, {"title": "text", "date": "date", "text": "text", "url": "keyword"})
    fields = get_fields(index)
    assert set(fields.keys()) == {"title", "date", "text", "url"}
    assert fields["title"].type == "text"
    assert fields["date"].type == "date"

    # default settings
    assert fields["date"].identifier is False

    # default settings depend on the type
    assert fields["date"].metareader.access == "read"
    assert fields["text"].metareader.access == "none"

    # Changing an existing field's type should throw an error
    with pytest.raises(ValueError):
        set_fields(index, {"title": PartialField(type="keyword")})
    refresh()
    set_fields(index, {"title": PartialField(client_settings={"foo": "bar"}, identifier=True)})

    assert get_fields(index)["title"].client_settings == {"foo": "bar"}
    assert get_fields(index)["title"].identifier is True


def test_field_description(index):
    set_fields(index, dict(test=PartialField(type="text", description="Dit is een test")))
    d = get_fields(index)
    assert d["test"].description == "Dit is een test"


def test_field_values(index):
    def value_set(field):
        return {v.value for v in field_values(index, field)}

    def value_descriptions(field):
        return {v.value: v.description for v in field_values(index, field)}

    set_fields(
        index,
        dict(
            tag=PartialField(
                type="tag", values=[FieldValue(value="a", description="A"), FieldValue(value="x", description="X")]
            ),
            kw=PartialField(type="keyword"),
        ),
    )
    assert value_set("tag") == {"a", "x"}
    assert value_set("kw") == set()
    upload_documents(index, [dict(tag=["a", "b"], kw="x"), dict(tag="a")])
    refresh_index(index)
    assert value_set("tag") == {"a", "b", "x"}
    assert value_set("kw") == {"x"}
    assert value_descriptions("tag") == {"a": "A", "x": "X", "b": None}
    assert value_descriptions("kw") == {"x": None}

    set_fields(index, dict(kw=PartialField(description="KW", values=[FieldValue(value="y", description="Y")])))
    assert value_descriptions("kw") == {"x": None, "y": "Y"}
