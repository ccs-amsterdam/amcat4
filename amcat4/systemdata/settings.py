from elasticsearch import NotFoundError

from amcat4.elastic import es
from amcat4.models import ImageObject, IndexId, ProjectSettings, Roles, ServerSettings
from amcat4.systemdata.roles import create_project_role
from amcat4.systemdata.versions import roles_index_name, settings_index_id, settings_index_name

## PROJECT INDEX SETTINGS


async def get_project_settings(index_id: str) -> ProjectSettings:
    id = settings_index_id(index_id)
    exclude = ["project_settings.image.base64"]
    elastic = await es()
    doc = (await elastic.get(index=settings_index_name(), id=id, source_excludes=exclude))["_source"]
    doc = doc["project_settings"]
    return ProjectSettings.model_validate(doc)


async def create_project_settings(index_settings: ProjectSettings, admin_email: str | None = None):
    """
    An index needs to exist in two places: as an elasticsearch index, and as a document in the settings index.
    This function creates the settings document, and optionally assigns an admin role to a user.
    It is called when creating a new index, and can be used to register existing/imported indices.
    """
    index_id = index_settings.id
    id = settings_index_id(index_settings.id)
    doc = dict(project_settings=index_settings.model_dump())
    elastic = await es()
    await elastic.create(index=settings_index_name(), id=id, document=doc, refresh=True)

    if admin_email:
        await create_project_role(admin_email, index_id, Roles.ADMIN)


async def update_project_settings(index_settings: ProjectSettings, ignore_missing: bool = False):
    id = settings_index_id(index_settings.id)
    doc = dict(project_settings=index_settings.model_dump(exclude_none=True))
    elastic = await es()
    await elastic.update(index=settings_index_name(), id=id, doc=doc, doc_as_upsert=ignore_missing, refresh=True)


async def delete_project_settings(index_id: str, ignore_missing: bool = False):
    if index_id.startswith("_"):  # avoid mistake allowing removal of server settings
        raise ValueError(f"{index_id} is not a project index")
    elastic = await es()
    try:
        await elastic.delete(index=settings_index_name(), id=index_id, refresh=True)
    except NotFoundError:
        if not ignore_missing:
            raise

    await elastic.delete_by_query(
        index=roles_index_name(),
        body={"query": {"term": {"role_context": index_id}}},
        refresh=True,
    )


async def get_project_image(index_id: IndexId) -> ImageObject | None:
    id = settings_index_id(index_id)
    include = ["project_settings.image"]
    elastic = await es()
    doc = (await elastic.get(index=settings_index_name(), id=id, source_includes=include))["_source"]
    if "image" not in doc["project_settings"]:
        return None
    return ImageObject.model_validate(doc["project_settings"].get("image"))


## SERVER SETTINGS


async def get_server_settings() -> ServerSettings:
    id = settings_index_id("_server")
    elastic = await es()
    try:
        doc = (await elastic.get(index=settings_index_name(), id=id))["_source"]
        doc = doc["server_settings"]
    except NotFoundError:
        return ServerSettings()
    return ServerSettings.model_validate(doc)


async def upsert_server_settings(server_settings: ServerSettings):
    id = settings_index_id("_server")
    doc = dict(server_settings=server_settings.model_dump(exclude_none=True))
    elastic = await es()
    await elastic.update(index=settings_index_name(), id=id, doc=doc, doc_as_upsert=True, refresh=True)
