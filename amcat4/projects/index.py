from typing import Iterable, Mapping


from amcat4.elastic import es
from amcat4.models import CreateField, FieldType, IndexSettings, Role, RoleRule, User
from amcat4.systemdata.fields import create_fields, list_fields
from amcat4.systemdata.roles import list_user_roles, raise_if_not_server_role
from amcat4.systemdata.settings import (
    create_project_settings,
    delete_project_settings,
    update_project_settings,
)
from amcat4.elastic.util import index_scan
from amcat4.systemdata.versions.v2 import SETTINGS_INDEX, settings_index_id


class IndexDoesNotExist(ValueError):
    pass


def raise_if_not_project_exists(index_id: str):
    if not es().exists(index=SETTINGS_INDEX, id=settings_index_id(index_id)):
        raise IndexDoesNotExist(f'Index "{index_id}" does not exist')


def create_project_index(new_index: IndexSettings, admin_email: str | None = None):
    """
    An index needs to exist in two places: as an elasticsearch index, and as a document in the settings index.
    This function creates the elasticsearch index first, and then creates the settings document.
    """
    index_id = settings_index_id(new_index.id)
    if es().exists(index=SETTINGS_INDEX, id=index_id):
        raise ValueError(f'Index "{id}" already exists')

    create_es_index(new_index.id)
    register_project_index(new_index, admin_email)


def register_project_index(
    index: IndexSettings, admin_email: str | None = None, mappings: Mapping[str, FieldType | CreateField] | None = None
):
    """
    Register an existing elasticsearch index in the settings index.
    The index must already exist in elasticsearch, and must not yet be registered.

    Field types are automatically inferred from the existing mappings.
    You can optionally provide field mappings to specify the field types before they are inferred.
    NOTE: the mappings argument is not yet used, but we need it if we want to support importing properly
    """
    if not es().indices.exists(index=index.id):
        raise ValueError(f'Index "{index.id}" does not exist in elasticsearch')
    if es().exists(index=SETTINGS_INDEX, id=settings_index_id(index.id)):
        raise ValueError(f'Index "{index.id}" is already registered')

    create_project_settings(index, admin_email)
    if mappings:
        create_fields(index.id, mappings)
    list_fields(index.id)  # This will infer field types from the existing mappings


def deregister_project_index(index_id: str):
    delete_project_settings(index_id)


def update_project_index(update_index: IndexSettings):
    """
    Update index settings
    """
    update_project_settings(update_index)


def delete_project_index(index_id: str, ignore_missing: bool = False):
    """
    Delete both the index and the index settings
    """
    _es = es().options(ignore_status=404) if ignore_missing else es()
    _es.indices.delete(index=index_id)
    delete_project_settings(index_id, ignore_missing)


def list_project_indices(ids: list[str] | None = None, source: list[str] | None = None) -> Iterable[IndexSettings]:
    """
    List all project indices, or only those with the given ids.
    """
    query = {"terms": {"_id": ids}} if ids else None
    for id, ix in index_scan(SETTINGS_INDEX, query=query, source=source):
        yield IndexSettings.model_validate(ix)


def create_es_index(index_id: str):
    es().indices.create(index=index_id, mappings={"dynamic": "strict", "properties": {}})


def refresh_index(index: str):
    """
    Refresh the elasticsearch index
    """
    es().indices.refresh(index=index)


def list_user_project_indices(user: User, show_all=False) -> Iterable[tuple[IndexSettings, RoleRule | None]]:
    """
    List all indices that a user has any role on.
    Return both the index and RoleRule that the user matched for that index (can be None if show_all is True)
    TODO: add pagination and search here
    """
    index_role_lookup: dict[str, RoleRule] = {}
    user_indices: list[str] = []
    for role in list_user_roles(user, required_role=Role.LISTER):
        index_role_lookup[role.role_context] = role
        user_indices.append(role.role_context)

    if show_all:
        raise_if_not_server_role(user, Role.ADMIN)
        indices = list_project_indices()
    else:
        indices = list_project_indices(ids=user_indices)

    for index in indices:
        yield index, index_role_lookup[index.id]
