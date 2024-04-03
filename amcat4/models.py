from curses import OK
from xml.dom.domreg import registered
import pydantic
from pydantic import BaseModel, field_validator, model_validator, validator
from typing import Annotated, Any, Literal
from typing_extensions import Self


FieldType = Literal[
    "text", "date", "boolean", "keyword", "number", "integer", "object", "vector", "geo_point", "image_url", "tag", "json"
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


class Field(BaseModel):
    """Settings for a field. Some settings, such as metareader, have a strict type because they are used
    server side. Others, such as client_settings, are free-form and can be used by the client to store settings."""

    type: FieldType
    elastic_type: ElasticType
    identifier: bool = False
    metareader: FieldMetareaderAccess = FieldMetareaderAccess()
    client_settings: dict[str, Any] = {}

    @model_validator(mode="after")
    def validate_type(self) -> Self:
        if self.identifier:
            # Identifiers have to be immutable. Instead of checking this in every endpoint that performs updates,
            # we can disable it for certain types that are known to be mutable.
            for forbidden_type in ["tag"]:
                if self.type == forbidden_type:
                    raise ValueError(f"Field type {forbidden_type} cannot be used as an identifier")
        return self


class CreateField(BaseModel):
    """Model for creating a field"""

    type: FieldType
    elastic_type: ElasticType | None = None
    identifier: bool = False
    metareader: FieldMetareaderAccess | None = None
    client_settings: dict[str, Any] | None = None


class UpdateField(BaseModel):
    """Model for updating a field"""

    type: FieldType | None = None
    metareader: FieldMetareaderAccess | None = None
    client_settings: dict[str, Any] | None = None


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
