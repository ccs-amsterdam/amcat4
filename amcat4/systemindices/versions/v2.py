from amcat4.elastic_mapping import ElasticMapping, nested_field, object_field
from amcat4.systemindices.util import SystemIndex, bulk_insert, BulkInsertAction, batched_index_scan, system_index_name
from amcat4.elastic_connection import _elastic_connection
from amcat4.settings import get_settings
from typing import Iterable

_contact_field = object_field(
    name={"type": "keyword"},
    email={"type": "keyword"},
    url={"type": "keyword"},
)

# The settings system index contains both server-wide settings and per-index settings.
# The index settings are stored in documents with id equal to the index name.
# The server settings are stored in the document with id "_server"
# Indices in elastic cannot start with an underscore, so there is no risk of collision.
settings_mapping: ElasticMapping = dict(
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
            ),
        ),
        welcome_buttons=nested_field(
            label={"type": "text"},
            href={"type": "keyword"},
        ),
    ),
)


fields_mapping: ElasticMapping = dict(
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
    ),
)

roles_mapping: ElasticMapping = dict(
    email={"type": "keyword"},
    index={"type": "keyword"},
    role={"type": "keyword"},
)

requests_mapping: ElasticMapping = dict(
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


def check_deprecated_version(index: str):
    global_doc = _elastic_connection().get(index=index, id="_global", source_includes="version")
    version = global_doc["_source"].get("version", 0)
    if version != 2:
        raise ValueError(
            "Cannot automatically migrate from current system index, because its a very old version. "
            "So old that we would be surprised if you ever even see this message, but if you do, "
            "and you really need to migrate, please contact us"
        )

def extract_server_settings(index: str, doc: dict):
    return BulkInsertAction(
        index=index,
        id="_server",
        doc={
            "server_settings": {
                "name": doc.get("name"),
                "description": None,
                "external_url": doc.get("external_url"),
                "welcome_text": doc.get("welcome_text"),
                "icon": doc.get("server_icon"),
                "information_links": doc.get("information_links"),
                "welcome_buttons": doc.get("welcome_buttons"),
                "contact": doc.get("contact"),
            }
        },
    )

def extract_index_settings(index: str, id: str, doc: dict):
    return BulkInsertAction(
        index=index,
        id=doc.get("id"),
        doc={
            "index_settings": {
                "name": doc.get("name"),
                "description": doc.get("description"),
                "contact": doc.get("contact"),
                "guest_role": doc.get("guest_role"),
                "archived": doc.get("archived"),
                "folder": doc.get("folder"),
                "image_url": doc.get("image_url"),
            }
        },
    )

def extract_index_roles(index: str, email: str, role: str, in_index: str):
    yield BulkInsertAction(
        index=index,
        id=f"{role.id}_{role.index}_{role.role}",
        doc={
            "index": role.index,
            "email": role.email,
            "role": role.role
        },
    )

def extract_requests(index: str, request: dict):
    yield BulkInsertAction(
        index=index,
        id=f"_server_{request.get('timestamp')}_{request.get('email')}",
        doc={
            "request_type": request.get("request_type"),
            "email": request.get("email"),
            "index": request.get("index", "_server"),
            "status": request.get("status"),
            "message": request.get("message"),
            "timestamp": request.get("timestamp"),
            "role": request.get("role"),
            "name": request.get("name"),
            "description": request.get("description"),
            "folder": request.get("folder"),
        },
    )

def extract_field(index: str, index_id: str, field: dict):
    field_name = field.get("field")
    if not field_name:
        return None
    return BulkInsertAction(
        index=index,
        id=f"{index_id}_{field_name}",
        doc={
            "field": field_name,
            "settings": field.get("settings", {}),
        },
    )


def migrate():
    version = 2
    settings_index = system_index_name(version, "settings")
    roles_index = system_index_name(version, "roles")
    fields_index = system_index_name(version, "fields")
    requests_index = system_index_name(version, "requests")

    v1_system_index = get_settings().system_index
    check_deprecated_version(v1_system_index)

    def bulk_generator() -> Iterable[BulkInsertAction]:
        for id, doc in batched_index_scan(v1_system_index):
            if id == '_global':
                # migrate server settings
                yield extract_server_settings(settings_index, doc)

                # migrate server roles
                for role in doc.get("roles", []):
                    yield extract_index_roles(roles_index, role.email, role.role, "_global")

                # migrate requests
                for request in doc.get("requests", []):
                    yield extract_requests(requests_index, request)

            else:
                # migrate index settings
                yield extract_index_settings(settings_index, id, doc)

                # migrate index roles
                for role in doc.get("roles", []):
                    yield extract_index_roles(roles_index, role.email, role.role, id)

                # migrate index fields
                for field in doc.get("fields", []):
                    field_name = field.get("field")
                    if not field_name:
                        continue
                    yield BulkInsertAction(
                        index=fields_index,
                        id=f"{id}_{field_name}",
                        doc={
                            "field": field_name,
                            "settings": field.get("settings", {}),
                        },
                    )


    bulk_insert(bulk_generator())


SYSTEM_INDICES = [
    SystemIndex(name="settings", mapping=settings_mapping),
    SystemIndex(name="fields", mapping=fields_mapping),
    SystemIndex(name="roles", mapping=roles_mapping),
    SystemIndex(name="requests", mapping=requests_mapping)
]
