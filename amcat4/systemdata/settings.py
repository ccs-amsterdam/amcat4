from elasticsearch import NotFoundError
from amcat4.systemdata.roles import update_role

from amcat4.systemdata.versions.v2 import SETTINGS_INDEX, settings_index_id
from amcat4.elastic import es
from amcat4.models import IndexSettings, Role, ServerSettings

## PROJECT INDEX SETTINGS


class IndexDoesNotExist(ValueError):
    pass


def get_project_settings(index_id: str) -> IndexSettings:
    id = settings_index_id(index_id)
    doc = es().get(index=SETTINGS_INDEX, id=id)["_source"]
    return IndexSettings.model_validate(doc)


def create_project_settings(index_settings: IndexSettings, admin_email: str | None = None):
    """
    An index needs to exist in two places: as an elasticsearch index, and as a document in the settings index.
    This function creates the settings document, and optionally assigns an admin role to a user.
    It is called when creating a new index, and can be used to register existing/imported indices.
    """
    index_id = index_settings.id
    if not es().indices.exists(index=index_id):
        raise ValueError(f"Index {index_id} does not exist")

    try:
        id = settings_index_id(index_settings.id)
        es().create(index=SETTINGS_INDEX, id=id, document=index_settings.model_dump(), refresh=True)
    except Exception as e:
        raise ValueError(f'Index "{index_id}" is already registered') from e

    if admin_email:
        update_role(admin_email, index_id, Role.ADMIN)


def update_project_settings(index_settings: IndexSettings):
    id = settings_index_id(index_settings.id)
    es().update(index=SETTINGS_INDEX, id=id, doc=index_settings.model_dump(), doc_as_upsert=True, refresh=True)


def delete_project_settings(index_id: str, ignore_missing: bool = False):
    if index_id.startswith("_"):  # _server
        raise ValueError(f"{index_id} is not a project index")
    try:
        es().delete(index=SETTINGS_INDEX, id=index_id, refresh=True)

    except NotFoundError:
        if not ignore_missing:
            raise


## SERVER SETTINGS


def get_server_settings() -> ServerSettings:
    id = settings_index_id("_server")
    doc = es().get(index=SETTINGS_INDEX, id=id)["_source"]
    return ServerSettings.model_validate(doc)


def upsert_server_settings(server_settings: ServerSettings):
    id = settings_index_id("_server")
    es().update(index=SETTINGS_INDEX, id=id, doc=server_settings.model_dump(), doc_as_upsert=True, refresh=True)
