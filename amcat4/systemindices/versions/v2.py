from amcat4.elastic_mapping import ElasticMappingProperties, nested_field, object_field
from amcat4.systemindices.util import SystemIndex
from amcat4.elastic_connection import _elastic_connection
from amcat4.settings import get_settings

_contact_field = object_field(
    name={"type": "keyword"},
    email={"type": "keyword"},
    url={"type": "keyword"},
)

# The settings system index contains both server-wide settings and per-index settings.
# The index settings are stored in documents with id equal to the index name.
# The server settings are stored in the document with id "_server"
# Indices in elastic cannot start with an underscore, so there is no risk of collision.
settings_mapping: ElasticMappingProperties = dict(
    index_settings=object_field(
        name={"type": "keyword"},
        description={"type": "text"},
        contact=_contact_field,
        guest_role={"type": "keyword"},
        archived={"type": "date"},
        folder={"type": "keyword"},
        image_url={"type": "keyword"},
    ),
    server_settings=object_field(
        name={"type": "keyword"},
        description={"type": "text"},
        contact=_contact_field,
        external_url={"type": "keyword"},
        welcome_text={"type": "text"},
        icon={"type": "keyword"},
        information_links=nested_field(
            title={"type": "text"},
            links=nested_field(
                label={"type": "text"},
                href={"type": "keyword"},
            )
        ),
        welcome_buttons=nested_field(
            label={"type": "text"},
            href={"type": "keyword"},
        ),
    )
)


fields_mapping: ElasticMappingProperties = dict(
    field={"type": "text"},
    settings=object_field(
        identifier={"type": "boolean"},
        type={"type": "text"},
        elastic_type={"type": "text"},
        client_settings=object_field(
            inDocument={"type": "boolean"},
            inList={"type": "boolean"},
            inListSummary={"type": "boolean"},
            isHeading={"type": "boolean"},
        ),
        metareader=object_field(
            access={"type": "text"},
            max_snippet=object_field(
                match_chars={"type": "integer"},
                max_matches={"type": "integer"},
                nomatch_chars={"type": "integer"},
            ),
        ),
    )
)

roles_mapping: ElasticMappingProperties = dict(
    email={"type": "keyword"},
    index={"type": "keyword"},
    role={"type": "keyword"},
)

requests_mapping: ElasticMappingProperties = dict(
    request_type={"type": "keyword"},
    email={"type": "keyword"},
    index={"type": "keyword"},
    status={"type": "keyword"},
    message={"type": "text"},
    timestamp={"type": "date"},
    role={"type": "keyword"},
    name={"type": "text"},
    description={"type": "text"},
    folder={"type": "keyword"},
)

v1_system_index = get_settings().system_index

def migrate_settings(migration_index):
   old_si =

   global_doc = _elastic_connection().get(index=si, id="_global", source_includes='version')
   version = global_doc["_source"].get("version", 0)
   if version != 2:
       raise ValueError(
           "Cannot automatically migrate from current system index, because its a very old version. "
           "So old that we would be surprised if you ever even see this message, but if you do, "
           "and you really need to migrate, please contact us"
       )



SYSTEM_INDICES = [
   SystemIndex(name="settings", mapping=mapping, migrate=None)
   SystemIndex(name="fields", mapping=mapping, migrate=None)
   SystemIndex(name="roles", mapping=mapping, migrate=None)
   SystemIndex(name="requests", mapping=mapping, migrate=None)
]
