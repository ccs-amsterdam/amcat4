from datetime import UTC, datetime
from typing import AsyncIterable, Mapping

from amcat4.connections import es, s3_enabled
from amcat4.elastic.util import index_scan
from amcat4.models import CreateDocumentField, FieldType, IndexId, ProjectSettings, RoleRule, Roles, User
from amcat4.objectstorage.multimedia import delete_project_multimedia
from amcat4.systemdata.fields import create_fields, list_fields
from amcat4.systemdata.roles import list_user_project_roles
from amcat4.systemdata.settings import (
    create_project_settings,
    delete_project_settings,
    get_project_settings,
    update_project_settings,
)
from amcat4.systemdata.versions import settings_index_id, settings_index_name


class IndexDoesNotExist(ValueError):
    pass


class IndexAlreadyExists(ValueError):
    pass


async def create_project_index(new_index: ProjectSettings, admin_email: str | None = None):
    """
    An index needs to exist in two places: as an elasticsearch index, and as a document in the settings index.
    This function creates the elasticsearch index first, and then creates the settings document.
    """
    index_exists = await es().indices.exists(index=new_index.id)
    project_exists = await es().exists(index=settings_index_name(), id=settings_index_id(new_index.id))
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

    await create_es_index(new_index.id)
    await register_project_index(new_index, admin_email)


async def register_project_index(
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
    await create_project_settings(index, admin_email)
    if mappings:
        await create_fields(index.id, mappings)
    await list_fields(index.id)  # This will infer field types from the existing mappings


async def deregister_project_index(index_id: str):
    await delete_project_settings(index_id)


async def update_project_index(update_index: ProjectSettings):
    """
    Update index settings
    """
    await update_project_settings(update_index)


async def archive_project_index(index_id: str, archived: bool):
    d = await get_project_settings(index_id)
    if d.archived is not None and archived:
        return

    if archived:
        archived_at = datetime.now(UTC)
        await es().update(
            index=settings_index_name(),
            id=settings_index_id(index_id),
            doc={"project_settings": {"archived": archived_at}},
            refresh=True,
        )
    else:
        await es().update(
            index=settings_index_name(),
            id=settings_index_id(index_id),
            script={"source": "ctx._source.project_settings.remove('archived')", "lang": "painless"},
            refresh=True,
        )


async def delete_project_index(index_id: str, ignore_missing: bool = False):
    """
    Delete both the index and the index settings, and the index bucket if any.
    """
    # important, because otherwise new project with same name will inherit old bucket
    # (buckets are always optional)
    # TODO: should we actually use unique index ids?
    if s3_enabled():
        await delete_project_multimedia(index_id)

    _es = es().options(ignore_status=404) if ignore_missing else es()
    await _es.indices.delete(index=index_id)

    await delete_project_settings(index_id, ignore_missing)


async def list_project_indices(ids: list[str] | None = None, skip_archived: bool = True) -> AsyncIterable[ProjectSettings]:
    """
    List all project indices, or only those with the given ids.
    """
    query = {"bool": {}}
    if ids is not None:
        query["bool"]["must"] = {"terms": {"_id": ids}}
    if skip_archived:
        query["bool"]["must_not"] = {"exists": {"field": "project_settings.archived"}}

    exclude_source = ["project_settings.image.base64", "server_settings"]

    async for id, ix in index_scan(settings_index_name(), query=query, exclude_source=exclude_source):
        if id.startswith("_"):
            continue
        project_settings = ix["project_settings"]
        yield ProjectSettings.model_validate(project_settings)


async def create_es_index(index_id: str):
    await es().indices.create(index=index_id, mappings={"dynamic": "strict", "properties": {}})


async def refresh_index(index: str):
    """
    Refresh the elasticsearch index
    """
    await es().indices.refresh(index=index)


async def list_user_project_indices(
    user: User, show_all=False, show_archived=False
) -> AsyncIterable[tuple[ProjectSettings, RoleRule | None]]:
    """
    List all indices that a user has any role on.
    Return both the index and RoleRule that the user matched for that index (can be None if show_all is True)
    TODO: add pagination and search here
    """
    if show_all:
        async for index in list_project_indices(skip_archived=not show_archived):
            yield index, RoleRule(role=Roles.ADMIN.name, role_context=index.id, email=user.email or "*")
        return

    project_role_lookup: dict[str, RoleRule] = {}
    user_indices: list[str] = []
    roles = await list_user_project_roles(user, required_role=Roles.LISTER)
    for role in roles:
        project_role_lookup[role.role_context] = role
        user_indices.append(role.role_context)

    async for index in list_project_indices(ids=user_indices, skip_archived=not show_archived):
        yield index, project_role_lookup[index.id]


async def index_size_in_bytes(index_id: IndexId) -> int:
    response = await es().indices.stats(
        index=index_id,
        metric="store",
    )
    return response["indices"][index_id]["total"]["store"]["size_in_bytes"]
