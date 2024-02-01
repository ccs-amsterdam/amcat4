import pydantic
from pydantic import BaseModel
from typing import Annotated, Literal, NewType


AmcatType = Literal["text", "date", "boolean", "keyword", "number", "object", "vector", "geo"]
ElasticType = Literal[
    "text",
    "annotated_text",
    "binary",
    "match_only_text",
    "date",
    "boolean",
    "keyword",
    "constant_keyword",
    "wildcard",
    "integer",
    "byte",
    "short",
    "long",
    "unsigned_long",
    "float",
    "half_float",
    "double",
    "scaled_float",
    "object",
    "flattened",
    "nested",
    "dense_vector",
    "geo_point",
]


class SnippetParams(BaseModel):
    """
    Snippet parameters for a specific field.
    nomatch_chars is the number of characters to show if there is no query match. This is always
    the first [nomatch_chars] of the field.
    """

    nomatch_chars: Annotated[int, pydantic.Field(ge=1)] = 100
    max_matches: Annotated[int, pydantic.Field(ge=0)] = 0
    match_chars: Annotated[int, pydantic.Field(ge=1)] = 50


class FieldClientDisplay(BaseModel):
    """Client display settings for a specific field."""

    in_list: bool = False
    in_list_summary: bool = False
    in_document: bool = True


class FieldMetareaderAccess(BaseModel):
    """Metareader access for a specific field."""

    access: Literal["none", "read", "snippet"] = "none"
    max_snippet: SnippetParams | None = None


class Field(BaseModel):
    """Settings for a field."""

    type: AmcatType
    elastic_type: ElasticType
    metareader: FieldMetareaderAccess = FieldMetareaderAccess()
    client_display: FieldClientDisplay = FieldClientDisplay()


class CreateField(BaseModel):
    """Model for creating a field"""

    elastic_type: ElasticType
    metareader: FieldMetareaderAccess | None = None
    client_display: FieldClientDisplay | None = None


class UpdateField(BaseModel):
    """Model for updating a field"""

    metareader: FieldMetareaderAccess | None = None
    client_display: FieldClientDisplay | None = None


def updateField(field: Field, update: UpdateField | Field):
    for key in update.model_fields_set:
        setattr(field, key, getattr(update, key))
    return field


FilterValue = str | int


class FilterSpec(BaseModel):
    """Form for filter specification."""

    values: list[FilterValue] | None = None
    gt: FilterValue | None = None
    lt: FilterValue | None = None
    gte: FilterValue | None = None
    lte: FilterValue | None = None
    exists: bool | None = None


class FieldSpec(BaseModel):
    """Form for field specification."""

    name: str
    snippet: SnippetParams | None = None


class SortSpec(BaseModel):
    """Form for sort specification."""

    order: Literal["asc", "desc"] = "asc"
