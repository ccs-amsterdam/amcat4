
# Version 2 splits the system index V1 into multiple indices.

from amcat4.system_index.mapping import eMapping, eObject, eObjectArray
from amcat4.system_index.util import SystemIndexSpec, Table

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

settings_mapping = eMapping(
    name='keyword',
    description='text',
    contact=eObject(
        name='keyword',
        email='keyword',
        url='keyword',
    ),

)



SI_Users_mapping: SI_ElasticMapping = {
    "email": {"type": "keyword"},
    "index": {"type": "keyword"},
    "role": {"type": "keyword"},
}





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



SPEC = SystemIndexSpec(
    version=1,
    tables=[
        Table(path='settings', model=SI_Settings, es_mapping=SI_Settings_mapping),
        Table(path='users', model=SI_Users, es_mapping=SI_Users_mapping),
        Table(path='requests', model=SI_Requests, es_mapping=SI_Requests_mapping)
    ]
)
