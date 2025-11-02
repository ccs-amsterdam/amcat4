from amcat4.elastic.connection import elastic_connection
from amcat4.elastic.mapping import ElasticMapping, nested_field, object_field
from amcat4.elastic.util import (
    SystemIndexMapping,
    system_index_name,
    es_bulk_create_or_overwrite,
    BulkInsertAction,
    index_scan,
)
from amcat4.config import get_settings
from typing import Iterable, Literal

from amcat4.multimedia.image_processing import create_image_from_url

VERSION = 2


def system_index(index: Literal["settings", "roles", "fields", "apikeys", "requests"]) -> str:
    return system_index_name(VERSION, index)


def settings_index_id(index: str | Literal["_server"]) -> str:
    return index


def roles_index_id(email: str, role_context: str | Literal["_server"]) -> str:
    return f"{role_context}:{email}"


def apikeys_index_id(email: str, name: str) -> str:
    return f"{email}:{name}"


def fields_index_id(index: str, name: str) -> str:
    return f"{index}:{name}"


def requests_index_id(type: str, email: str, project_id: str | None) -> str:
    return f"{type}:{project_id or ''}:{email}"


_contact_field = object_field(
    name={"type": "keyword"},
    email={"type": "keyword"},
    url={"type": "keyword"},
)

_image_field = object_field(
    id={"type": "keyword"},
    base64={"type": "binary"},
)

# The settings system index contains both server-wide settings and project settings.
# The project settings are stored in documents with id equal to the project index name.
# The server settings are stored in the document with id "_server"
# Indices in elastic cannot start with an underscore, so there is no risk of collision.
settings_mapping: ElasticMapping = dict(
    project_settings=object_field(
        id={"type": "keyword"},
        name={"type": "keyword"},
        description={"type": "text"},
        contact=_contact_field,
        archived={"type": "date"},
        folder={"type": "keyword"},
        image=_image_field,
    ),
    server_settings=object_field(
        id={"type": "keyword"},
        name={"type": "keyword"},
        description={"type": "text"},
        contact=_contact_field,
        external_url={"type": "keyword"},
        welcome_text={"type": "text"},
        icon=_image_field,
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
    email={"type": "keyword"},  # can also be *@domain.com (domain match) or * (guest match)
    role_context={"type": "keyword"},  # either _server or an index name
    role={"type": "keyword"},  # "NONE", "LISTER", "METAREADER", "READER", "WRITER", "ADMIN"
    # API KEY PROPOSAL:
    # Users can create an API key for their _server and index roles
    # The API key is stored hashed in the roles document.
    # The unhashed key is only shown once, when created.
    # A bearer token header with the API key can be used instead of middlecat auth.
    # a _server api key gives full user rights. An index api key gives rights only for that index
    # the api_key_role is the role that the api key has been granted, which has to be equal or lower than the users role
    api_key=object_field(
        hash={"type": "keyword"},
        expires={"type": "date"},
        role={"type": "keyword"},
        dpop_public_key={"type": "text"},  # for DPoP-bound API keys
    ),
)

apikey_mapping: ElasticMapping = dict(
    email={"type": "keyword"},  # api key is always linked to user email
    name={"type": "keyword"},  # user-given name. Has to be unique per user
    secret_key={"type": "keyword"},  # random unique key
    role_context={"type": "keyword"},  # either _server or an index name
    max_role={"type": "keyword"},  # role is min(user role, max_role)
    expires={"type": "date"},  # hard expiration date
    last_used={"type": "date"},  # update with a 15 minute debounce on use
    timeout_minutes={"type": "integer"},  # expire if now > last_used + timeout_minutes + 15 (debounce)
    dpop_public_key={"type": "keyword"},  # for DPoP-bound API keys
)


requests_mapping: ElasticMapping = dict(
    type={"type": "keyword"},
    email={"type": "keyword"},
    project_id={"type": "keyword"},
    status={"type": "keyword"},  # "pending", "approved", "rejected"
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
    global_doc = elastic_connection().get(index=index, id="_global", source_includes="version")
    version = global_doc["_source"].get("version", 0)
    if version != 2:
        raise ValueError(
            "Cannot automatically migrate from current system index, because its a very old version. "
            "So old that we would be surprised if you ever even see this message, but if you do, "
            "and you really need to migrate, please contact us. Or may we recommend a fresh start...? :)"
        )


def migrate_server_settings(doc: dict):
    return BulkInsertAction(
        index=system_index("settings"),
        id=settings_index_id("_server"),
        doc={
            "server_settings": {
                "name": doc.get("name"),
                "description": None,
                "external_url": doc.get("external_url"),
                "welcome_text": doc.get("welcome_text"),
                "icon": create_image_from_url(doc.get("server_icon")),
                "information_links": doc.get("information_links"),
                "welcome_buttons": doc.get("welcome_buttons"),
                "contact": doc.get("contact"),
            }
        },
    )


def migrate_project_settings(index: str, doc: dict):
    return BulkInsertAction(
        index=system_index("settings"),
        id=settings_index_id(index),
        doc={
            "project_settings": {
                "name": doc.get("name"),
                "description": doc.get("description"),
                "contact": doc.get("contact"),
                "archived": doc.get("archived"),
                "folder": doc.get("folder"),
                "image": create_image_from_url(doc.get("image_url")),
            }
        },
    )


def migrate_roles(role: dict, in_index: str | None):
    email = role.get("email", "")
    doc = {
        "role_context": in_index if in_index else "_server",
        "email": email,
        "role": role.get("role"),
        "role_match": "DOMAIN" if email.startswith("*@") else "EXACT",
    }

    return BulkInsertAction(index=system_index("roles"), id=roles_index_id(doc["email"], doc["index"]), doc=doc)


def migrate_guest_roles(role: dict, in_index: str | None):
    # these used to be index settings, but are now roles
    doc = {
        "index": in_index if in_index else "_server",
        "email": role.get("email"),
        "role": "*",
        "role_match": "ANY",
    }

    return BulkInsertAction(index=system_index("roles"), id=roles_index_id(doc["email"], doc["index"]), doc=doc)


def migrate_fields(index: str, field: dict):
    doc = {
        "index": index,
        "field": field.get("field"),
        "settings": field.get("settings", {}),
    }
    return BulkInsertAction(index=system_index("fields"), id=fields_index_id(index, doc["field"]), doc=doc)


SYSTEM_INDICES = [
    SystemIndexMapping(name="settings", mapping=settings_mapping),
    SystemIndexMapping(name="fields", mapping=fields_mapping),
    SystemIndexMapping(name="roles", mapping=roles_mapping),
    SystemIndexMapping(name="requests", mapping=requests_mapping),
]


def migrate():
    # v1 had just one big, bad index that used (whats now) the system indices prefix without version or path
    v1_system_index = system_index_name(1, "")
    check_deprecated_version(v1_system_index)

    def bulk_generator() -> Iterable[BulkInsertAction]:
        for id, doc in index_scan(v1_system_index):
            # The _global document in the v1 index contained server settings, server roles and all requests
            if id == "_global":
                yield migrate_server_settings(doc)

                for role in doc.get("roles", []):
                    yield migrate_roles(role, None)

            # The other documents had the index name as id, and contained index settings, index roles and fields
            else:
                yield migrate_project_settings(id, doc)

                for role in doc.get("roles", []):
                    yield migrate_roles(role, id)

                for field in doc.get("fields", []):
                    yield migrate_fields(id, field)

    es_bulk_create_or_overwrite(bulk_generator())
