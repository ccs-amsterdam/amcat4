from typing import Annotated, Any, Literal

import pydantic
from pydantic import BaseModel, model_validator
from typing_extensions import Self

FieldType = Literal[
    "text",
    "date",
    "boolean",
    "keyword",
    "number",
    "integer",
    "object",
    "vector",
    "geo_point",
    "image",
    "video",
    "audio",
    "tag",
    "json",
    "url",
]
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


class FieldMetareaderAccess(BaseModel):
    """Metareader access for a specific field."""

    access: Literal["none", "read", "snippet"] = "none"
    max_snippet: SnippetParams | None = None


class FieldValue(BaseModel):
    value: str
    description: str | None = None


class PartialField(BaseModel):
    """Class for updates to a field"""

    type: FieldType | None = None
    elastic_type: ElasticType | None = None
    identifier: bool = False
    metareader: FieldMetareaderAccess | None = None
    client_settings: dict[str, Any] | None = None
    description: str | None = None
    values: list[FieldValue] | None = None


class Field(PartialField):
    """Settings for a field. Some settings, such as metareader, have a strict type because they are used
    server side. Others, such as client_settings, are free-form and can be used by the client to store settings."""

    # Note: Python forces subclasses to have default values if superclass had them
    #       As a workaround, add a dummy default value, but force a value in the constructor
    type: FieldType = None  # type: ignore
    elastic_type: ElasticType = None  # type: ignore

    def __init__(self, type: FieldType, elastic_type: ElasticType, **data):
        super().__init__(type=type, elastic_type=elastic_type, **data)


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
