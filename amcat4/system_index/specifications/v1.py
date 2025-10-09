# Version 1 is the first version of the system index.
# It kept all data in a single index.

from amcat4.system_index.mapping import create_pydantic_model_from_mapping
from amcat4.system_index.util import SystemIndexSpec, Table
from amcat4.system_index.mapping import SI_ElasticMapping


SI_IndexList_mapping: SI_ElasticMapping = {
    "archived": {"type": "text"},
    "branding": {"type": "object", "properties": {
        "server_name": {"type": "text"},
        "server_icon": {"type": "keyword"},
        "server_url": {"type": "keyword"},
        "welcome_text": {"type": "text"},
    }},
    "client_data": {"type": "text"},
    "contact": {"type": "object", "properties": {
        "name": {"type": "keyword"},
        "email": {"type": "keyword"},
        "url": {"type": "keyword"},
    }},
    "description": {"type": "text"},
    "external_url": {"type": "keyword"},
    "fields": {"type": "nested", "properties": {
        "field": {"type": "text"},
        "settings": {"type": "object", "properties": {
            "identifier": {"type": "boolean"},
            "type": {"type": "text"},
            "elastic_type": {"type": "text"},
            "client_settings": {"type": "object", "properties": {
                "inDocument": {"type": "boolean"},
                "inList": {"type": "boolean"},
                "inListSummary": {"type": "boolean"},
                "isHeading": {"type": "boolean"},
            }},
            "metareader": {"type": "object", "properties": {
                "access": {"type": "text"},
                "max_snippet": {"type": "object", "properties": {
                    "match_chars": {"type": "integer"},
                    "max_matches": {"type": "integer"},
                    "nomatch_chars": {"type": "integer"},
                }}
            }},
        }},
    }},
    "folder": {"type": "keyword"},
    "guest_role": {"type": "keyword"},
    "image_url": {"type": "keyword"},
    "name": {"type": "text"},
    "requests": {"type": "nested", "properties": {
        "description": {"type": "text"},
        "email": {"type": "keyword"},
        "index": {"type": "keyword"},
        "message": {"type": "text"},
        "name": {"type": "text"},
        "reject": {"type": "boolean"},
        "role": {"type": "keyword"},
        "timestamp": {"type": "date"},
    }},
    "roles": {"type": "nested", "properties": {
        "email": {"type": "keyword"},
        "role": {"type": "keyword"},
    }},
    "version": {"type": "integer"},
}


SI_IndexList = create_pydantic_model_from_mapping("SI_IndexList", SI_IndexList_mapping)

test = SI_IndexList(banaan=4)



SPEC = SystemIndexSpec(
    version=1,
    tables=[
        Table(path='', model=SI_IndexList, es_mapping=SI_IndexList_mapping)
    ]
)
