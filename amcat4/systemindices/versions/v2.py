from amcat4.elastic_connection import _elastic_connection
from amcat4.elastic_mapping import ElasticMapping, nested_field, object_field
from amcat4.systemindices.util import SystemIndex, system_index_name, bulk_insert, BulkInsertAction, batched_index_scan
from amcat4.config import get_settings
from typing import Iterable

VERSION = 2

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
    index={"type": "keyword"},
    name={"type": "keyword"},
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
    status={"type": "keyword"}, # "pending", "approved", "rejected"
    message={"type": "text"},
    timestamp={"type": "date"},
    role={"type": "keyword"},
    name={"type": "text"},
    description={"type": "text"},
    folder={"type": "keyword"},
)


def check_deprecated_version(index: str):
    """
    The v1 system has a deprecated form of versioning, where the version number was stored in the _global document.
    The oldest versions should (pretty please...) no longer be used, so we don't support automatic migration from them.
    """
    global_doc = _elastic_connection().get(index=index, id="_global", source_includes="version")
    version = global_doc["_source"].get("version", 0)
    if version != 2:
        raise ValueError(
            "Cannot automatically migrate from current system index, because its a very old version. "
            "So old that we would be surprised if you ever even see this message, but if you do, "
            "and you really need to migrate, please contact us. Or may we recommend a fresh start...? :)"
        )


def migrate_server_settings(doc: dict):
    settings_index = system_index_name(VERSION, "settings")

    return BulkInsertAction(
        index=settings_index,
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

def migrate_index_settings(index: str, doc: dict):
    settings_index = system_index_name(VERSION, "settings")

    return BulkInsertAction(
        index=settings_index,
        id=index,
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


def migrate_roles(role: dict, in_index: str):
    roles_index = system_index_name(VERSION, "roles")

    return BulkInsertAction(
        index=roles_index,
        id=None,
        doc={
            "index": in_index,
            "email": role.get("email"),
            "role": role.get("role"),
        }
    )


def migrate_requests(request: dict):
    requests_index = system_index_name(VERSION, "requests")

    return BulkInsertAction(
        index=requests_index,
        id=None,
        doc={
            "request_type": request.get("request_type"),
            "email": request.get("email"),
            "index": request.get("index", "_server"),  # now use _server instead of None
            "status": "pending",  # before approved and rejected requests were removed
            "message": request.get("message"),
            "timestamp": request.get("timestamp"),
            "role": request.get("role"),
            "name": request.get("name"),
            "description": request.get("description"),
            "folder": request.get("folder"),
        },
    )


def migrate_fields(index: str, field: dict):
    fields_index = system_index_name(VERSION, "fields")

    return BulkInsertAction(
        index=fields_index,
        id=None,
        doc={
            "index": index,
            "field": field.get('field'),
            "settings": field.get("settings", {}),
        },
    )


SYSTEM_INDICES = [
    SystemIndex(name="settings", mapping=settings_mapping),
    SystemIndex(name="fields", mapping=fields_mapping),
    SystemIndex(name="roles", mapping=roles_mapping),
    SystemIndex(name="requests", mapping=requests_mapping)
]


def migrate():
    # v1 had just one big, bad index that used (whats now) the system indices prefix without version or path
    v1_system_index = get_settings().system_index
    check_deprecated_version(v1_system_index)

    def bulk_generator() -> Iterable[BulkInsertAction]:
        for id, doc in batched_index_scan(v1_system_index):
            ## The _global document in the v1 index contained server settings, server roles and all requests
            if id == '_global':
                yield migrate_server_settings(doc)

                for role in doc.get("roles", []):
                    yield migrate_roles(role, "_server")

                for request in doc.get("requests", []):
                    yield migrate_requests(request)

            ## The other documents had the index name as id, and contained index settings, index roles and fields
            else:
                yield migrate_index_settings(id, doc)

                for role in doc.get("roles", []):
                    yield migrate_roles(role, id)

                for field in doc.get("fields", []):
                    yield migrate_fields(id, field)


    bulk_insert(bulk_generator())
