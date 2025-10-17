from enum import IntEnum
import pydantic
from datetime import datetime
from pydantic import BaseModel, EmailStr, model_validator, Field as pydanticField
from typing import Annotated, Any, Literal, Union
from typing_extensions import Self


class User(BaseModel):
    email: EmailStr | None
    superadmin: bool = False


IndexId = Annotated[str, pydanticField(pattern=r"^[a-z][a-z0-9_-]*$")]
RoleEmailPattern = EmailStr | Literal["*"]  # user@domain.com or *@domain.com or *
RoleContext = IndexId | Literal["_server"]


class Role(IntEnum):
    NONE = 0
    LISTER = 10
    METAREADER = 20
    READER = 30
    WRITER = 40
    ADMIN = 50


class RoleRule(BaseModel):
    email_pattern: RoleEmailPattern
    role_context: RoleContext
    role: Role

    @model_validator(mode="after")
    def validate_role(self) -> Self:
        uses_wildcard = "*" in self.email_pattern
        if self.role == Role.ADMIN and uses_wildcard:
            raise ValueError(
                f"Cannot create ADMIN role for {self.email_pattern}. Only exact email matches can have ADMIN role"
            )
        return self


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


class ContactInfo(BaseModel):
    """Contact information for server or index maintainers"""

    name: str | None = None
    email: str | None = None
    url: str | None = None


class Links(BaseModel):
    label: str
    href: str


class LinksGroup(BaseModel):
    title: str
    links: list[Links]


class AbstractRequest(BaseModel):
    email: str
    timestamp: datetime | None = None
    message: str | None = None
    status: Literal["pending", "approved", "rejected"] = "pending"


class RoleRequest(AbstractRequest):
    request_type: Literal["role"] = "role"
    role_context: IndexId | Literal["_server"]
    role: Role


class CreateProjectRequest(AbstractRequest):
    request_type: Literal["create_project"] = "create_project"
    role_context: IndexId
    email: str
    description: str | None = None
    name: str | None = None
    folder: str | None = None


PermissionRequest = Annotated[Union[RoleRequest, CreateProjectRequest], pydantic.Field(discriminator="request_type")]


class IndexSettings(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    folder: str | None = None
    image_url: str | None = None
    contact: list[ContactInfo] | None = None
    archived: str | None = None


class ServerSettings(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    contact: list[ContactInfo] | None = None
    external_url: str | None = None
    welcome_text: str | None = None
    icon: str | None = None
    information_links: list[LinksGroup] | None = None
    welcome_buttons: list[Links] | None = None
