from typing import Iterable, Mapping


from amcat4.elastic import es
from amcat4.models import CreateDocumentField, FieldType, IndexId, ProjectSettings, Roles, RoleRule, User
from amcat4.objectstorage.s3bucket import delete_index_bucket, s3_enabled
from amcat4.systemdata.fields import create_fields, list_fields

from amcat4.systemdata.roles import list_user_project_roles
from amcat4.systemdata.settings import (
    create_project_settings,
    delete_project_settings,
    update_project_settings,
)
from amcat4.elastic.util import index_scan
from amcat4.systemdata.versions import system_index, settings_index_id


class IndexDoesNotExist(ValueError):
    pass


class IndexAlreadyExists(ValueError):
    pass


def create_project_index(new_index: ProjectSettings, admin_email: str | None = None):
    """
    An index needs to exist in two places: as an elasticsearch index, and as a document in the settings index.
    This function creates the elasticsearch index first, and then creates the settings document.
    """
    index_exists = es().indices.exists(index=new_index.id)
    project_exists = es().exists(index=system_index("settings"), id=settings_index_id(new_index.id))
    if index_exists and project_exists:
        raise IndexAlreadyExists(f'Project "{new_index.id}" already exists')
    if index_exists and not project_exists:
        # Note that we should not automatically register, because it's not certain the user is the original owner.
        # Need to create some process for server admins to import/register existing indices.
        raise IndexAlreadyExists(
            f'Elasticsearch index "{new_index.id}" already exists, but is not yet registered as a project index',
        )
    if not index_exists and project_exists:
        # We don't yet have a process to recover from this. We could just create the index and update the settings?
        raise IndexAlreadyExists(
            f'Project index "{new_index.id}" is already registered, but the elasticsearch index does not exist',
        )

    create_es_index(new_index.id)
    register_project_index(new_index, admin_email)


def register_project_index(
    index: ProjectSettings,
    admin_email: str | None = None,
    mappings: Mapping[str, FieldType | CreateDocumentField] | None = None,
):
    """
    Register an existing elasticsearch index in the settings index.
    The index must already exist in elasticsearch, and must not yet be registered.

    Field types are automatically inferred from the existing mappings.
    You can optionally provide field mappings to specify the field types before they are inferred.
    NOTE: the mappings argument is not yet used, but we need it if we want to support importing properly
    """
    create_project_settings(index, admin_email)
    if mappings:
        create_fields(index.id, mappings)
    list_fields(index.id)  # This will infer field types from the existing mappings


def deregister_project_index(index_id: str):
    delete_project_settings(index_id)


def update_project_index(update_index: ProjectSettings):
    """
    Update index settings
    """
    update_project_settings(update_index)


def delete_project_index(index_id: str, ignore_missing: bool = False):
    """
    Delete both the index and the index settings, and the index bucket if any.
    """
    _es = es().options(ignore_status=404) if ignore_missing else es()
    _es.indices.delete(index=index_id)

    # important, because otherwise new project with same name will inherit old bucket
    # (buckets are always optional)
    if s3_enabled():
        delete_index_bucket(index_id, True)

    delete_project_settings(index_id, ignore_missing)


def list_project_indices(ids: list[str] | None = None) -> Iterable[ProjectSettings]:
    """
    List all project indices, or only those with the given ids.
    """
    query = {"terms": {"_id": ids}} if ids is not None else None
    exclude_source = ["project_settings.image.base64", "server_settings.icon.base64"]

    for id, ix in index_scan(system_index("settings"), query=query, exclude_source=exclude_source):
        project_settings = ix["project_settings"]
        yield ProjectSettings.model_validate(project_settings)


def create_es_index(index_id: str):
    es().indices.create(index=index_id, mappings={"dynamic": "strict", "properties": {}})


def refresh_index(index: str):
    """
    Refresh the elasticsearch index
    """
    es().indices.refresh(index=index)


def list_user_project_indices(user: User, show_all=False) -> Iterable[tuple[ProjectSettings, RoleRule | None]]:
    """
    List all indices that a user has any role on.
    Return both the index and RoleRule that the user matched for that index (can be None if show_all is True)
    TODO: add pagination and search here
    """
    if show_all:
        for index in list_project_indices():
            yield index, RoleRule(role=Roles.ADMIN.name, role_context=index.id, email=user.email or "*")
        return

    project_role_lookup: dict[str, RoleRule] = {}
    user_indices: list[str] = []
    for role in list_user_project_roles(user, required_role=Roles.LISTER):
        project_role_lookup[role.role_context] = role
        user_indices.append(role.role_context)

    for index in list_project_indices(ids=user_indices):
        yield index, project_role_lookup[index.id]


def index_size_in_bytes(index_id: IndexId) -> int:
    response = es().indices.stats(
        index=index_id,
        metric="store",
    )
    return response["indices"][index_id]["total"]["store"]["size_in_bytes"]
