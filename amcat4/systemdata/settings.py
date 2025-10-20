from elasticsearch import ConflictError, NotFoundError
from fastapi import HTTPException
from starlette.types import HTTPExceptionHandler

from amcat4.systemdata.roles import create_project_role, update_project_role
from amcat4.systemdata.versions.v2 import ROLES_INDEX, SETTINGS_INDEX, settings_index_id
from amcat4.elastic import es
from amcat4.models import ProjectSettings, Roles, ServerSettings

## PROJECT INDEX SETTINGS


class IndexDoesNotExist(ValueError):
    pass


def get_project_settings(index_id: str) -> ProjectSettings:
    id = settings_index_id(index_id)
    try:
        doc = es().get(index=SETTINGS_INDEX, id=id)["_source"]
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Index {id} does not exist")

    try:
        doc = doc["project_settings"]
        return ProjectSettings.model_validate(doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading settings for index {id}: {e}") from e


def create_project_settings(index_settings: ProjectSettings, admin_email: str | None = None):
    """
    An index needs to exist in two places: as an elasticsearch index, and as a document in the settings index.
    This function creates the settings document, and optionally assigns an admin role to a user.
    It is called when creating a new index, and can be used to register existing/imported indices.
    """
    index_id = index_settings.id
    if not es().indices.exists(index=index_id):
        raise HTTPException(status_code=404, detail=f"Elastic index {index_id} does not exist")

    try:
        id = settings_index_id(index_settings.id)
        doc = dict(project_settings=index_settings.model_dump())
        es().create(index=SETTINGS_INDEX, id=id, document=doc, refresh=True)
    except ConflictError as e:
        raise HTTPException(status_code=400, detail=f'Index "{index_id}" is already registered') from e
    except Exception as e:
        raise e

    if admin_email:
        create_project_role(admin_email, index_id, Roles.ADMIN)


def update_project_settings(index_settings: ProjectSettings):
    id = settings_index_id(index_settings.id)
    doc = dict(project_settings=index_settings.model_dump())
    es().update(index=SETTINGS_INDEX, id=id, doc=doc, doc_as_upsert=True, refresh=True)


def delete_project_settings(index_id: str, ignore_missing: bool = False):
    if index_id.startswith("_"):  # avoid mistake allowing removal of server settings
        raise ValueError(f"{index_id} is not a project index")
    try:
        es().delete(index=SETTINGS_INDEX, id=index_id, refresh=True)
    except NotFoundError:
        if not ignore_missing:
            raise

    es().delete_by_query(
        index=ROLES_INDEX,
        body={"query": {"term": {"role_context": index_id}}},
        refresh=True,
    )


## SERVER SETTINGS


def get_server_settings() -> ServerSettings:
    id = settings_index_id("_server")
    try:
        doc = es().get(index=SETTINGS_INDEX, id=id)["_source"]
        doc = doc["server_settings"]
    except NotFoundError:
        return ServerSettings(id=id)
    return ServerSettings.model_validate(doc)


def upsert_server_settings(server_settings: ServerSettings):
    id = settings_index_id("_server")
    doc = dict(server_settings=server_settings.model_dump())
    es().update(index=SETTINGS_INDEX, id=id, doc=doc, doc_as_upsert=True, refresh=True)
