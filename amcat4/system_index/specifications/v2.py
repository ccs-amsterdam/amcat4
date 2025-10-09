
# Version 2 splits the system index V1 into multiple indices.

from typing_extensions import Annotated
import pydantic
from pydantic import BaseModel
from typing import Literal, Optional, Union
from amcat4.system_index.mapping import SI_ElasticMapping, create_pydantic_model_from_mapping
from amcat4.system_index.util import SystemIndexSpec, Table
from amcat4.models import Branding, ContactInfo, Field, Links, LinksGroup, PermissionRequest
from datetime import datetime


# SETTINGS TABLE ----------------------------------------------------

SI_Settings_mapping: SI_ElasticMapping = {
    "name": {"type": "keyword"},
    "description": {"type": "text"},
    "contact": {"type": "flattened"},
    "type": {"type": "keyword"},
    # Index specific
    "guest_role": {"type": "keyword"},
    "archived": {"type": "date"},
    "folder": {"type": "keyword"},
    "image_url": {"type": "keyword"},
    "fields": {"type": "flattened"},
    # Server specific
    "external_url": {"type": "keyword"},
    "welcome_text": {"type": "text"},
    "information_links": {"type": "flattened"},
    "welcome_buttons": {"type": "flattened"},
    "icon": {"type": "keyword"},
}

SI_Settings = create_pydantic_model_from_mapping("SI_Settings", SI_Settings_mapping)


# USERS TABLE ------------------------------------------------------------

SI_Users_mapping: SI_ElasticMapping = {
    "email": {"type": "keyword"},
    "index": {"type": "keyword"},
    "role": {"type": "keyword"},
}


SI_Users = create_pydantic_model_from_mapping("SI_Users", SI_Users_mapping)


# REQUESTS TABLE ----------------------------------------------------------

SI_Requests_mapping: SI_ElasticMapping = {
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

SI_Requests = create_pydantic_model_from_mapping("SI_Requests", SI_Requests_mapping)


SPEC = SystemIndexSpec(
    version=1,
    tables=[
        Table(path='settings', model=SI_Settings, es_mapping=SI_Settings_mapping),
        Table(path='users', model=SI_Users, es_mapping=SI_Users_mapping),
        Table(path='requests', model=SI_Requests, es_mapping=SI_Requests_mapping)
    ]
)
