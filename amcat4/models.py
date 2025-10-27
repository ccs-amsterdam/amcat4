from enum import IntEnum
from datetime import datetime, UTC
from pydantic import BaseModel, EmailStr, model_validator, Field
from typing import Annotated, Any, Literal, Union
from typing_extensions import Self


class User(BaseModel):
    """For internal use only. Represents an authenticated user."""

    email: EmailStr | None  # this can only be an authenticed, full email address or None for unauthenticated users
    superadmin: bool = False  # if auth is disabled, or if the user is the hardcoded admin email
    auth_disabled: bool = False  # if auth is disabled on this server


IndexId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]*$", title="Index ID")]
IndexIds = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]*(,[a-z][a-z0-9_-]*)*$", title="Index ID or comma-separated IDs")]


######################## ROLE SPECIFICATIONS #########################


class Roles(IntEnum):
    NONE = 0
    LISTER = 10
    METAREADER = 20
    READER = 30
    WRITER = 40
    ADMIN = 50


Role = Literal["NONE", "LISTER", "METAREADER", "READER", "WRITER", "ADMIN"]
GuestRole = Literal["NONE", "LISTER", "METAREADER", "READER", "WRITER"]
ServerRole = Literal["NONE", "WRITER", "ADMIN"]


RoleEmailPattern = Annotated[
    EmailStr | Literal["*"],
    Field(title="An email addres (user@domain.com), domain wildcard (*@domain.com) or guest wildcard (*)"),
]  # user@domain.com or *@domain.com or *
RoleContext = Annotated[IndexId | Literal["_server"], Field(title="Index ID for project roles or _server for server roles")]


class RoleRule(BaseModel):
    email: RoleEmailPattern
    role_context: RoleContext
    role: Role

    @model_validator(mode="after")
    def validate_role(self) -> Self:
        uses_wildcard = "*" in self.email
        if self.role == Roles.ADMIN and uses_wildcard:
            raise ValueError(f"Cannot create ADMIN role for {self.email}. Only exact email matches can have ADMIN role")
        return self


######################## DOCUMENT FIELD SPECIFICATIONS #########################

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

    nomatch_chars: Annotated[int, Field(ge=1)] = 100
    max_matches: Annotated[int, Field(ge=0)] = 0
    match_chars: Annotated[int, Field(ge=1)] = 50


class DocumentFieldMetareaderAccess(BaseModel):
    """Metareader access for a specific field."""

    access: Literal["none", "read", "snippet"] = "none"
    max_snippet: SnippetParams | None = None


class DocumentField(BaseModel):
    """Settings for a field. Some settings, such as metareader, have a strict type because they are used
    server side. Others, such as client_settings, are free-form and can be used by the client to store settings."""

    type: FieldType
    elastic_type: ElasticType
    identifier: bool = False
    metareader: DocumentFieldMetareaderAccess = DocumentFieldMetareaderAccess()
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


class CreateDocumentField(BaseModel):
    """Model for creating a field"""

    type: FieldType
    elastic_type: ElasticType | None = None
    identifier: bool = False
    metareader: DocumentFieldMetareaderAccess | None = None
    client_settings: dict[str, Any] | None = None


class UpdateDocumentField(BaseModel):
    """Model for updating a field"""

    type: FieldType | None = None
    metareader: DocumentFieldMetareaderAccess | None = None
    client_settings: dict[str, Any] | None = None


####################### SEARCH SPECIFICATIONS #########################

FilterValue = str | int


class FilterSpec(BaseModel):
    """Form for filter specification."""

    values: list[FilterValue] | None = None
    gt: FilterValue | None = None
    lt: FilterValue | None = None
    gte: FilterValue | None = None
    lte: FilterValue | None = None
    exists: bool | None = None

    monthnr: int | None = None
    dayofweek: str | None = None


class FieldSpec(BaseModel):
    """Form for field specification."""

    name: str
    snippet: SnippetParams | None = None


class SortSpec(BaseModel):
    """Form for sort specification."""

    order: Literal["asc", "desc"] = "asc"


###################### PERMISSION REQUESTS #########################


class ServerRoleRequest(BaseModel):
    type: Literal["server_role"]
    role: Role = Field(description="The server role being requested.")
    message: str | None = Field(
        default=None,
        description="Message to the server administrators to explain who you are and why you need this server role.",
    )


class ProjectRoleRequest(BaseModel):
    type: Literal["project_role"]
    project_id: IndexId = Field(description="ID of the project for which the role is requested.")
    role: Role = Field(description="The project role being requested.")
    message: str | None = Field(
        default=None,
        description="Message to the project administrators to explain who you are and why you need this project role.",
    )


class CreateProjectRequest(BaseModel):
    type: Literal["create_project"]
    project_id: IndexId = Field(description="ID for the new project.")
    name: str | None = Field(default=None, description="Optional name for the new project.")
    description: str | None = Field(default=None, description="Optional description for the new project.")
    folder: str | None = Field(default=None, description="Optional folder for the new project.")
    message: str | None = Field(
        default=None, description="Message to explain the purpose of this project, and any details relevant to its approval."
    )


PermissionRequest = Annotated[
    Union[ServerRoleRequest, ProjectRoleRequest, CreateProjectRequest],
    Field(discriminator="type", description="The permission request."),
]


class AdminPermissionRequest(BaseModel):
    email: EmailStr = Field(description="Email address of the user making the request.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Timestamp of the request.")
    status: Literal["approved", "rejected", "pending"] = Field(default="pending", description="Status of the request.")
    request: PermissionRequest


####################### PROJECT AND SERVER SETTINGS #########################


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


class ImageObject(BaseModel):
    hash: str
    base64: str | None = None


class ProjectSettings(BaseModel):
    id: IndexId
    name: str | None = None
    description: str | None = None
    folder: str | None = None
    image: ImageObject | None = None
    contact: list[ContactInfo] | None = None
    archived: str | None = None


class ServerSettings(BaseModel):
    name: str | None = None
    description: str | None = None
    contact: list[ContactInfo] | None = None
    external_url: str | None = None
    welcome_text: str | None = None
    icon: ImageObject | None = None
    information_links: list[LinksGroup] | None = None
    welcome_buttons: list[Links] | None = None
