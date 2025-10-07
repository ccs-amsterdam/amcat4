# Version 1 is the first version of the system index.
# It kept all data in a single index.

from pydantic import BaseModel
from typing import Literal, Optional, Iterable
import elasticsearch.helpers
from amcat4.elastic_connection import _elastic_connection
from amcat4.system_index.util import SystemIndexSpec, Table, get_system_index_name
from amcat4.models import ContactInfo, Roles, Field, Branding

# System Index (SI) index specifications -----------------------------


class SI_IndexList(BaseModel):
    id: str
    archived: Optional[str]
    branding: Optional[Branding]
    client_data: Optional[str]
    contact: Optional[list[ContactInfo]]
    description: Optional[str]
    external_url: Optional[str]
    fields: Optional[dict[str, Field[str, Field]]]
    folder: Optional[str]
    guest_role: Literal["NONE", "METAREADER", "READER", "WRITER"]
    image_url: Optional[str]
    name: Optional[str]
    requests: Optional[list[dict]]
    roles: list[Roles]
    version: Optional[int]


SI_IndexList_mapping = {
    "archived": {"type": "text"},
    "branding": {"type": "object"},
    "client_data": {"type": "text"},
    "contact": {"type": "object"},
    "description": {"type": "text"},
    "external_url": {"type": "keyword"},
    "fields": {"type" "object"},
    "folder": {"type": "keyword"},
    "guest_role": {"type": "keyword"},
    "image_url": {"type": "keyword"},
    "name": {"type": "text"},
    "requests": {"type": "nested"},
    "roles": {"type": "nested"},
    "version": {"type": "integer"},
}


SPEC = SystemIndexSpec(
    version=1,
    tables=[
        Table(path='', model=SI_IndexList, es_mapping=SI_IndexList_mapping)
    ]
)


def export_index_list() -> Iterable[SI_IndexList]:
    si = get_system_index_name(SPEC.version)
    elastic = _elastic_connection()

    # There used to be an even older version with an older migration method.
    # We don't support migrating from that version anymore.
    global_doc = elastic.get(index=si, id="_global", source_includes='version')
    version = global_doc["_source"].get("version", 0)
    if version != 2:
        raise ValueError(
            "Cannot automatically migrate from current system index, because its a very old version. "
            "So old that we would be surprised if you ever even see this message, but if you do, "
            "and you really need to migrate, please contact us"
        )

    for entry in elasticsearch.helpers.scan(elastic, index=si, _source=True):
        yield SI_IndexList(
            id=entry["_id"],
            archived=entry["_source"].get("archived"),
            branding=entry["_source"].get("branding"),
            client_data=entry["_source"].get("client_data"),
            contact=entry["_source"].get("contact"),
            description=entry["_source"].get("description"),
            external_url=entry["_source"].get("external_url"),
            fields=entry["_source"].get("fields"),
            folder=entry["_source"].get("folder"),
            guest_role=entry["_source"].get("guest_role", "NONE"),
            image_url=entry["_source"].get("image_url"),
            name=entry["_source"].get("name"),
            requests=entry["_source"].get("requests"),
            roles=[Roles(**r) for r in entry["_source"].get("roles", [])],
            version=entry["_source"].get("version")
        )
