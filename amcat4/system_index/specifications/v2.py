
# Version 2 splits the system index V1 into multiple indices.

from pydantic import BaseModel
from typing import Literal, Optional
from amcat4.system_index.util import SystemIndexSpec, Table
from amcat4.models import ContactInfo, Field, Links, LinksGroup
from datetime import datetime


# INDEX LIST TABLE ----------------------------------------------------
class SI_IndexList(BaseModel):
    id: str
    name: str
    description: Optional[str]
    guest_role: Literal["NONE", "METAREADER", "READER", "WRITER"]
    archived: Optional[str]
    folder: Optional[str]
    image_url: Optional[str]
    fields: Optional[dict[str, Field]]
    contact: Optional[list[ContactInfo]]


SI_IndexList_mapping = {
    "name": {"type": "text"},
    "description": {"type": "text"},
    "guest_role": {"type": "keyword"},
    "fields": {"type": "object"},
    "archived": {"type": "date"},
    "folder": {"type": "keyword"},
    "image_url": {"type": "keyword"},
    "external_url": {"type": "keyword"},
}


# SERVER SETTINGS TABLE ----------------------------------------------------
class SI_ServerSettings(BaseModel):
    id: str
    name: Optional[str]
    description: Optional[str]
    server_name: Optional[str]
    server_url: Optional[str]
    welcome_text: Optional[str]
    server_icon: Optional[str]
    welcome_buttons: Optional[list[Links]]
    information_links: Optional[list[LinksGroup]]
    contact: Optional[list[ContactInfo]]


SI_ServerSettings_mapping = {
    "name": {"type": "text"},
    "branding": {"type": "object"},
    "description": {"type": "text"},
    "server_name": {"type": "keyword"},
    "server_url": {"type": "keyword"},
    "welcome_text": {"type": "text"},
    "server_icon": {"type": "keyword"},
    "welcome_buttons": {"type": "object"},
    "information_links": {"type": "object"},
    "contact": {"type": "object"},
}


# USERS TABLE ------------------------------------------------------------
class SI_Users(BaseModel):
    email: str
    index: str   # global for global roles
    role: Literal["NONE", "METAREADER", "READER", "WRITER", "ADMIN"]


SI_Users_mapping = {
    "email": {"type": "keyword"},
    "index": {"type": "keyword"},
    "role": {"type": "keyword"},
}


# REQUESTS TABLE ----------------------------------------------------------
class AbstractRequest(BaseModel):
    email: str
    timestamp: datetime | None = None
    message: str | None = None
    status: Literal["PENDING", "APPROVED", "REJECTED", "CANCELED"] = "PENDING"


class SI_RoleRequest(AbstractRequest):
    request_type: Literal["role"] = "role"
    index: str | None = None
    role: Literal["NONE", "METAREADER", "READER", "WRITER", "ADMIN"]


class SI_CreateProjectRequest(AbstractRequest):
    request_type: Literal["create_project"] = "create_project"
    index: str
    email: str
    description: str | None = None
    name: str | None = None
    folder: str | None = None


SI_Requests_mapping = {
    "request_type": {"type": "keyword"},
    "email": {"type": "keyword"},
    "index": {"type": "keyword"},
    "status": {"type": "keyword"},
    "message": {"type": "text"},
    "timestamp": {"type": "date"},
    "role": {"type": "keyword"},
    "name": {"type": "text"},
    "description": {"type": "text"},
    "folder": {"type": "keyword"},
}


SPEC = SystemIndexSpec(
    version=1,
    tables=[
        Table(path='index_list', model=SI_IndexList, es_mapping=SI_IndexList_mapping),
        Table(path='server_settings', model=SI_ServerSettings, es_mapping=SI_ServerSettings_mapping),
        Table(path='users', model=SI_Users, es_mapping=SI_Users_mapping),
        Table(path='requests', model=[SI_RoleRequest, SI_CreateProjectRequest], es_mapping=SI_Requests_mapping)
    ]
)
