# This is a copy of all the models in amcat4.models.py that are used in v1.

import pydantic
from pydantic import BaseModel, model_validator
from typing import Annotated, Any, Literal
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
    nomatch_chars: Annotated[int, pydantic.Field(ge=1)] = 100
    max_matches: Annotated[int, pydantic.Field(ge=0)] = 0
    match_chars: Annotated[int, pydantic.Field(ge=1)] = 50


class FieldMetareaderAccess(BaseModel):
    access: Literal["none", "read", "snippet"] = "none"
    max_snippet: SnippetParams | None = None


class Field(BaseModel):
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


class ContactInfo(BaseModel):
    name: str | None = None
    email: str | None = None
    url: str | None = None


class Roles(BaseModel):
    role: Literal["NONE", "METAREADER", "READER", "WRITER", "ADMIN"]
    email: str


class Branding(BaseModel):
    server_name: str | None = None
    server_icon: str | None = None
    server_url: str | None = None
    welcome_text: str | None = None
    client_data: str | None = None
