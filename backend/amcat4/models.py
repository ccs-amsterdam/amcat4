from datetime import UTC, datetime
from enum import IntEnum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from typing_extensions import Self

_IX = r"[a-z0-9][a-z0-9_-]*"
IndexId = Annotated[str, Field(pattern=rf"^{_IX}$", title="Index ID")]


######################## ROLE SPECIFICATIONS #########################


class Roles(IntEnum):
    NONE = 0
    OBSERVER = 10
    METAREADER = 20
    READER = 30
    WRITER = 40
    ADMIN = 50


Role = Literal["NONE", "OBSERVER", "METAREADER", "READER", "WRITER", "ADMIN"]
GuestRole = Literal["NONE", "OBSERVER", "METAREADER", "READER", "WRITER"]
ServerRole = Literal["NONE", "WRITER", "ADMIN"]


NO_AUTH_USER = Literal["ADMIN"]

RoleEmailPattern = Annotated[
    EmailStr | Literal["*"] | NO_AUTH_USER,
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
        if self.role == Roles.ADMIN.name and uses_wildcard:
            raise ValueError(f"Cannot have ADMIN role for {self.email}. Only exact email matches can have ADMIN role")
        return self


###################### USER AND API KEY SPECIFICATIONS ##########################


class ApiKeyRestrictions(BaseModel):
    edit_api_keys: bool | None = None
    server_role: Role | None = None
    default_project_role: Role | None = None
    project_roles: dict[IndexId, Role] | None = None


class ApiKey(BaseModel):
    email: EmailStr
    name: str
    hashed_key: str
    restrictions: ApiKeyRestrictions
    expires_at: datetime
    jkt: str | None = None


AuthMethod = Literal["middlecat", "api_key", "oidc", "none"]


class User(BaseModel):
    """For internal use only. Represents a user (authenticated, no-auth, or guest)."""

    email: (
        EmailStr | NO_AUTH_USER | None
    )  # email address, NO_AUTH_USER ("ADMIN") if auth is disabled, or None for unauthenticated guests
    superadmin: bool = False  # if auth is disabled, or if the user is the hardcoded admin email
    auth_disabled: bool = False  # if auth is disabled on this server
    api_key_name: str | None = None  # if logged in via API key, what is its name
    api_key_restrictions: ApiKeyRestrictions | None = None  # If logged in via API key, what are the role restrictions
    auth_method: AuthMethod = "none"


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
    "url",
]


class SnippetParams(BaseModel):
    """
    Snippet parameters for a specific field (in words).
    - If there are query matches, return at most max_matches fragments of words_per_match words around the matches.
    - If there are no matches (or max_matches is 0), return the first nomatch_words words of the field.
    """

    model_config = ConfigDict(extra="forbid")  # catch old (character based) parameters

    nomatch_words: Annotated[int, Field(ge=0)] = 20
    max_matches: Annotated[int, Field(ge=0)] = 0
    words_per_match: Annotated[int, Field(ge=1)] = 10


class DocumentFieldMetareaderAccess(BaseModel):
    """
    What users with the METAREADER role can do with a field.
    - access: whether they can see the field: not at all (none), only as a snippet, or completely (read)
    - queryable: whether they can use the field in queries and filters. By default (None) this is the same as whether
      they can see the field. A field can be queryable but not visible (e.g. for non-consumptive research: you can
      count how often a word occurs, but not read the text), or visible but not queryable.
    """

    access: Literal["none", "read", "snippet"] = "none"
    max_snippet: SnippetParams | None = None
    queryable: bool | None = None

    @property
    def can_query(self) -> bool:
        return self.queryable if self.queryable is not None else self.access != "none"


class DocumentFieldReaderAccess(BaseModel):
    """
    What users with the READER role can do with a field (WRITER and ADMIN can always see and query all fields).
    """

    visible: bool = True
    queryable: bool | None = None  # by default, the same as visible

    @property
    def can_query(self) -> bool:
        return self.queryable if self.queryable is not None else self.visible


class DocumentField(BaseModel):
    """Settings for a field. Some settings, such as metareader, have a strict type because they are used
    server side. Others, such as client_settings, are free-form and can be used by the client to store settings."""

    type: FieldType
    # Unique fields: documents with the same values for all unique fields are considered the same document
    unique: bool = False
    metareader: DocumentFieldMetareaderAccess = DocumentFieldMetareaderAccess()
    reader: DocumentFieldReaderAccess = DocumentFieldReaderAccess()
    client_settings: dict[str, Any] = {}
    # If set, the field is in a "sort slot" (date, number or keyword), which makes sorting on it fast
    sort_slot: Literal["date", "number", "keyword"] | None = None

    @model_validator(mode="after")
    def validate_access(self) -> Self:
        if self.unique and self.type in ("tag", "vector", "object"):
            raise ValueError(f"A {self.type} field cannot be unique")
        if not self.reader.visible and self.metareader.access != "none":
            raise ValueError("A field that is not visible for readers cannot be visible for metareaders")
        if not self.reader.can_query and self.metareader.can_query:
            raise ValueError("A field that is not queryable for readers cannot be queryable for metareaders")
        if self.metareader.access == "snippet" and self.type != "text":
            raise ValueError("Snippets are only possible for text fields")
        return self


class DocumentFieldDefinition(BaseModel):
    type: FieldType
    unique: bool | None = None


class CreateDocumentField(DocumentFieldDefinition):
    """Model for creating a field"""

    metareader: DocumentFieldMetareaderAccess | None = None
    reader: DocumentFieldReaderAccess | None = None
    client_settings: dict[str, Any] | None = None


class UpdateDocumentField(BaseModel):
    """Model for updating a field"""

    name: str | None = Field(default=None, description="Rename the field")
    type: FieldType | None = Field(
        default=None, description="Change the type of the field. Existing values are converted (or an error is raised)"
    )
    unique: bool | None = None
    metareader: DocumentFieldMetareaderAccess | None = None
    reader: DocumentFieldReaderAccess | None = None
    client_settings: dict[str, Any] | None = None
    fast_sort: bool | None = Field(
        default=None,
        description="Put this field in the (date, number or keyword) sort slot of the project, which makes sorting "
        "on this field fast. A project can have one field per sort slot.",
    )


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
    id: str
    base64: str | None = None


class ProjectSettings(BaseModel):
    id: IndexId
    name: str | None = None
    description: str | None = None
    folder: str | None = None
    image: ImageObject | None = None
    contact: list[ContactInfo] | None = None
    archived: datetime | None = None


class ServerSettings(BaseModel):
    name: str | None = None
    description: str | None = None
    contact: list[ContactInfo] | None = None
    external_url: str | None = None
    welcome_text: str | None = None
    icon: ImageObject | None = None
    information_links: list[LinksGroup] | None = None
    welcome_buttons: list[Links] | None = None


####################### OBJECT STORAGE SPECIFICATIONS #########################


AllowedContentType = Literal[
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/bmp",
    "image/webp",
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
    "audio/m4a",
]


class RegisterObject(BaseModel):
    filepath: str = Field(description="The original filename of the multimedia object. Can include directories.")
    size: int = Field(gt=0, description="The exact (!) size of the multimedia file in bytes")
    content_type: AllowedContentType | None = Field(
        default=None,
        description="The MIME type of the multimedia file (e.g., image/jpeg, video/mp4). "
        "If None, it will be inferred from the file extension.",
    )
    force: bool = Field(
        default=False,
        description="Whether to force re-uploading the object if it already exists with the same size",
    )


class ObjectStorage(BaseModel):
    index: IndexId
    field: str
    filepath: str
    path: str
    size: int
    content_type: AllowedContentType | None = None
    registered: datetime | None = None
    last_synced: datetime | None = None
