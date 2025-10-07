
# Version 2 splits the system index V1 into multiple indices.

from pydantic import BaseModel
from typing import Literal, Optional
import elasticsearch.helpers
from amcat4.elastic_connection import _elastic_connection
from amcat4.system_index.util import SystemIndexSpec, Table, create_or_refresh_system_index, get_system_index_name
from amcat4.models import ContactInfo, Field, Links, LinksGroup
from amcat4.system_index import system_index_v1 as v1
from datetime import datetime
import json


# TODO: think about whether we want to keep the 'current' version of each amcat4.models model in the version files.
# If we don't, we can't 'change' them (only add keys). If we do, we have to keep them in sync,
# (or import the models from the last system_index version, which might make sense?)
#
# For models that haven't changed, we'd then import them here and re-assign them
# Field = v1.Field


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
    "archived": {"type": "date"},
    "folder": {"type": "keyword"},
    "image_url": {"type": "keyword"},
    "branding": {"type": "object"},
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
    reject: bool = False
    cancel: bool = False


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


# The system index specification bundles the version and the models for validating and mapping
# the system index tables.
SPEC = SystemIndexSpec(
    version=1,
    tables=[
        Table(path='index_list', model=SI_IndexList, es_mapping=SI_IndexList_mapping),
        Table(path='server_settings', model=SI_ServerSettings, es_mapping=SI_ServerSettings_mapping),
        Table(path='users', model=SI_Users, es_mapping=SI_Users_mapping),
        Table(path='requests', model=[SI_RoleRequest, SI_CreateProjectRequest], es_mapping=SI_Requests_mapping)
    ]
)


def import_index_list(v1_ix: v1.SI_IndexList):
    si_index_list = get_system_index_name(SPEC.version, 'index_list')

    doc = SI_IndexList(
        id=v1_ix.id,
        name=v1_ix.name or "",
        description=v1_ix.description,
        guest_role=v1_ix.guest_role,
        archived=v1_ix.archived,
        folder=v1_ix.folder,
        image_url=v1_ix.image_url,
        contact=v1_ix.contact,
        fields=v1_ix.fields
    )

    doc_dict = doc.model_dump()
    id = doc_dict.pop('id')

    _elastic_connection().index(
        index=si_index_list,
        id=id,
        document=doc_dict,
    )


def import_users(v1_ix: v1.SI_IndexList):
    si_users = get_system_index_name(SPEC.version, 'users')

    actions = []
    for role in v1_ix.roles:
        doc = SI_Users(
            email=role.email,
            index=v1_ix.id,
            role=role.role
        )
        actions.append({
            "_index": si_users,
            "_id": f"{doc.email}_{doc.index}",
            "_source": doc.model_dump()
        })

    if len(actions) > 0:
        elasticsearch.helpers.bulk(_elastic_connection(), actions)


def import_server_settings(vi_global: v1.SI_IndexList):
    si_server_settings = get_system_index_name(SPEC.version, 'server_settings')

    # V2 does specify the client data
    client_data = json.loads(vi_global.client_data or "{}")
    branding = vi_global.branding or {}

    doc = SI_ServerSettings(
        id="server_settings",
        name=vi_global.name,
        description=None,
        server_name=branding.get("server_name"),
        server_url=branding.get('server_url'),
        welcome_text=branding.get('welcome_text'),
        server_icon=branding.get('server_icon'),
        welcome_buttons=client_data.get("welcome_buttons"),
        information_links=client_data.get("information_links"),
        contact=vi_global.contact,
    )

    doc_dict = doc.model_dump()
    id = doc_dict.pop('id')
    _elastic_connection().index(
        index=si_server_settings,
        id=id,
        document=doc_dict,
    )


def import_requests(v1_global: v1.SI_IndexList):
    si_requests = get_system_index_name(SPEC.version, 'requests')

    actions = []
    for r in v1_global.requests or []:
        type = r.get("request_type")
        if type == 'role':
            doc = SI_RoleRequest(**r)
        else:
            doc = SI_CreateProjectRequest(**r)

        actions.append({
            "_index": si_requests,
            "_id": f"{doc.request_type}_{doc.email}_{doc.index or '_global'}",
            "_source": doc.model_dump()
        })

    if len(actions) > 0:
        elasticsearch.helpers.bulk(_elastic_connection(), actions)


def migrate():
    create_or_refresh_system_index(SPEC)

    for ix in v1.export_index_list():
        if ix.id == "_global":
            import_server_settings(ix)
            import_requests(ix)
            import_users(ix)
        else:
            import_index_list(ix)
            import_users(ix)


# Here we would add the export functions (like in v1) in case we would need to migrate to v3.
# (and we can also use this to serialize and back-up the system index)
# def export_index_list(): ...
