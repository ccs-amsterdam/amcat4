# Version 1 is the first version of the system index.
# It kept all data in a single index.

from pydantic import BaseModel
from typing import Literal, Optional
from amcat4.system_index.util import SystemIndexSpec, Table
from amcat4.system_index.specifications.v1_models import ContactInfo, Roles, Field, Branding

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
