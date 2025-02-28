import pytest

from amcat4.fields import field_values, get_fields, set_fields
from amcat4.index import refresh_index, upload_documents
from amcat4.models import FieldValue, PartialField


def test_field_description(index):
    set_fields(index, dict(test=PartialField(type="text", description="Dit is een test")))
    d = get_fields(index)
    assert d["test"].description == "Dit is een test"


def test_field_values(index):
    set_fields(
        index,
        dict(
            tag=PartialField(
                type="tag", values=[FieldValue(value="a", description="A"), FieldValue(value="x", description="X")]
            )
        ),
    )
    assert set(field_values(index, "tag")) == {"a", "x"}
    upload_documents(index, [dict(tag=["a", "b"]), dict(tag="a")])
    refresh_index(index)
    assert set(field_values(index, "tag")) == {"a", "b"}
