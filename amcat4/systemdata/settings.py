from elasticsearch import NotFoundError
from amcat4.systemdata.roles import elastic_create_or_update_role, elastic_list_roles
from amcat4.systemdata.util import index_scan
from amcat4.systemdata.versions.v2 import SETTINGS_INDEX, settings_index_id
from amcat4.elastic import es
from amcat4.models import IndexSettings, ServerSettings

## INDEX SETTINGS


class IndexDoesNotExist(ValueError):
    pass


def elastic_index_exists(index_id: str) -> bool:
    return bool(es().exists(index=SETTINGS_INDEX, id=settings_index_id(index_id)))


def elastic_get_index_settings(index_id: str) -> IndexSettings:
    id = settings_index_id(index_id)
    doc = es().get(index=SETTINGS_INDEX, id=id)["_source"]
    return IndexSettings.model_validate(doc)


def elastic_create_or_update_index_settings(index_settings: IndexSettings):
    """
    Create or update index settings
    """
    id = settings_index_id(index_settings.id)
    es().update(index=SETTINGS_INDEX, id=id, doc=index_settings.model_dump(), doc_as_upsert=True, refresh=True)


def create_index_settings(index_settings: IndexSettings, admin_email: str | None = None):
    """
    An index needs to exist in two places: as an elasticsearch index, and as a document in the settings index.
    This function creates the settings document, and optionally assigns an admin role to a user.
    """
    index_id = index_settings.id
    if not es().indices.exists(index=index_id):
        raise ValueError(f"Index {index_id} does not exist")
    if es().exists(index=SETTINGS_INDEX, id=index_id):
        raise ValueError(f"Index {index_id} is already registered")

    elastic_create_or_update_index_settings(index_settings)
    if admin_email:
        elastic_create_or_update_role(admin_email, index_id, "ADMIN")


def update_index_settings(index_settings: IndexSettings):
    elastic_create_or_update_index_settings(index_settings)


def delete_index_settings(index_id: str, ignore_missing: bool = False):
    try:
        es().delete(index=SETTINGS_INDEX, id=index_id, refresh=True)
    except NotFoundError:
        if not ignore_missing
            raise



## SERVER SETTINGS

def elastic_get_server_settings() -> ServerSettings:
    id = settings_index_id('_server')
    doc = es().get(index=SETTINGS_INDEX, id=id)["_source"]
    return ServerSettings.model_validate(doc)


def elastic_create_or_update_server_settings(server_settings: ServerSettings):
    id = settings_index_id("_server")
    es().update(index=SETTINGS_INDEX, id=id, doc=server_settings.model_dump(), doc_as_upsert=True, refresh=True)
