import uuid
from typing import AsyncGenerator, Literal

from amcat4.connections import es
from amcat4.elastic.mapping import ElasticMapping, nested_field, object_field
from amcat4.elastic.util import (
    BulkInsertAction,
    SystemIndexMapping,
    es_bulk_create,
    index_scan,
    system_index_name,
)
from amcat4.objectstorage.image_processing import create_image_from_url

VERSION = 2


def settings_index_name() -> str:
    return system_index_name(VERSION, "settings")


def roles_index_name() -> str:
    return system_index_name(VERSION, "roles")


def fields_index_name() -> str:
    return system_index_name(VERSION, "fields")


def apikeys_index_name() -> str:
    return system_index_name(VERSION, "apikeys")


def requests_index_name() -> str:
    return system_index_name(VERSION, "requests")


def objectstorage_index_name() -> str:
    return system_index_name(VERSION, "objectstorage")


def settings_index_id(index: str | Literal["_server"]) -> str:
    return index


def roles_index_id(email: str, role_context: str | Literal["_server"]) -> str:
    return f"{role_context}:{email}"


def fields_index_id(index: str, name: str) -> str:
    return f"{index}:{name}"


def requests_index_id(type: str, email: str, project_id: str | None) -> str:
    return f"{type}:{project_id or ''}:{email}"


def objectstorage_index_id(index: str, field: str, filepath: str) -> str:
    id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{field}/{filepath}"))
    return f"{index}:{id}"


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
        name={"type": "text"},
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
)

apikey_mapping: ElasticMapping = dict(
    email={"type": "keyword"},  # api key is always linked to user email
    name={"type": "keyword"},  # user-given name. Has to be unique per user
    hashed_key={"type": "keyword"},
    expires_at={"type": "date"},  # hard expiration date
    jkt={"type": "keyword"},  # JSON web key thumbprint for DPoP
    restrictions=object_field(
        ## API keys share the roles from the user email, but within optional restrictions
        edit_api_keys={"type": "boolean"},  # can create and modify the user's own api keys
        server_role={"type": "keyword"},  # max role on server
        default_project_role={"type": "keyword"},  # max role on projects without specific role
        project_roles=nested_field(  # max role on specific projects
            project_id={"type": "keyword"},
            role={"type": "keyword"},
        ),
    ),
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


objectstorage_mapping: ElasticMapping = dict(
    index={"type": "keyword"},
    field={"type": "keyword"},
    filepath={"type": "wildcard"},
    path={"type": "keyword"},
    size={"type": "long"},
    content_type={"type": "keyword"},
    registered={"type": "date"},
    last_synced={"type": "date"},
)


async def check_deprecated_version(index: str):
    """
    The v1 system has a deprecated form of versioning, where the version number was stored in the _global document.
    The oldest versions should (pretty please...) no longer be used, so we don't support automatic migration from them.
    """
    global_doc = await es().get(index=index, id="_global", source_includes="version")
    version = global_doc["_source"].get("version", 0)
    if version != 2:
        raise ValueError(
            "Cannot automatically migrate from current system index, because its a very old version. "
            "So old that we would be surprised if you ever even see this message, but if you do, "
            "and you really need to migrate, please contact us. Or may we recommend a fresh start...? :)"
        )


async def migrate_server_settings(doc: dict):
    return BulkInsertAction(
        index=settings_index_name(),
        id=settings_index_id("_server"),
        doc={
            "server_settings": {
                "name": doc.get("name"),
                "description": None,
                "external_url": doc.get("external_url"),
                "welcome_text": doc.get("welcome_text"),
                "icon": await create_image_from_url(doc.get("server_icon")),
                "information_links": doc.get("information_links"),
                "welcome_buttons": doc.get("welcome_buttons"),
                "contact": doc.get("contact"),
            }
        },
    )


async def migrate_project_settings(index: str, doc: dict):
    return BulkInsertAction(
        index=settings_index_name(),
        id=settings_index_id(index),
        doc={
            "project_settings": {
                "name": doc.get("name"),
                "description": doc.get("description"),
                "contact": doc.get("contact"),
                "archived": doc.get("archived"),
                "folder": doc.get("folder"),
                "image": await create_image_from_url(doc.get("image_url")),
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

    return BulkInsertAction(index=roles_index_name(), id=roles_index_id(doc["email"], doc["index"]), doc=doc)


def migrate_guest_roles(role: dict, in_index: str | None):
    # these used to be index settings, but are now roles
    doc = {
        "index": in_index if in_index else "_server",
        "email": role.get("email"),
        "role": "*",
        "role_match": "ANY",
    }

    return BulkInsertAction(index=roles_index_name(), id=roles_index_id(doc["email"], doc["index"]), doc=doc)


def migrate_fields(index: str, field: dict):
    doc = {
        "index": index,
        "field": field.get("field"),
        "settings": field.get("settings", {}),
    }
    return BulkInsertAction(index=fields_index_name(), id=fields_index_id(index, doc["field"]), doc=doc)


SYSTEM_INDICES = [
    SystemIndexMapping(name="settings", mapping=settings_mapping),
    SystemIndexMapping(name="fields", mapping=fields_mapping),
    SystemIndexMapping(name="roles", mapping=roles_mapping),
    SystemIndexMapping(name="apikeys", mapping=apikey_mapping),
    SystemIndexMapping(name="requests", mapping=requests_mapping),
    SystemIndexMapping(name="objectstorage", mapping=objectstorage_mapping),
]


async def migrate():
    # v1 had just one big, bad index that used (whats now) the system indices prefix without version or path
    v1_system_index = system_index_name(1, "")
    await check_deprecated_version(v1_system_index)

    async def bulk_generator() -> AsyncGenerator[BulkInsertAction]:
        async for id, doc in index_scan(v1_system_index):
            # The _global document in the v1 index contained server settings, server roles and all requests
            if id == "_global":
                yield await migrate_server_settings(doc)

                for role in doc.get("roles", []):
                    yield migrate_roles(role, None)

            # The other documents had the index name as id, and contained index settings, index roles and fields
            else:
                yield await migrate_project_settings(id, doc)

                for role in doc.get("roles", []):
                    yield migrate_roles(role, id)

                for field in doc.get("fields", []):
                    yield migrate_fields(id, field)

    await es_bulk_create(bulk_generator(), overwrite=True)
