from psycopg.types.json import Jsonb

from amcat4.errors import NotFoundError
from amcat4.models import ImageObject, IndexId, ProjectSettings, Roles, ServerSettings
from amcat4.postgres.connection import connection, execute, fetch_one
from amcat4.systemdata.roles import create_project_role

## PROJECT INDEX SETTINGS

_PROJECT_COLUMNS = ["name", "description", "folder", "contact", "image", "archived"]
_JSON_COLUMNS = {"contact", "image"}


def _project_from_row(row: dict, include_image_data: bool = False) -> ProjectSettings:
    d = {k: row[k] for k in ["id", *_PROJECT_COLUMNS] if k in row}
    if d.get("image") and not include_image_data:
        d["image"] = {"id": d["image"]["id"]}
    return ProjectSettings.model_validate(d)


async def get_project_settings(index_id: str) -> ProjectSettings:
    row = await fetch_one("SELECT * FROM projects WHERE id = %s", [index_id])
    if row is None:
        raise NotFoundError(f"Project {index_id} does not exist")
    return _project_from_row(row)


def _values(settings: ProjectSettings, exclude_none: bool) -> dict:
    d = settings.model_dump(exclude_none=exclude_none, exclude={"id"})
    return {k: (Jsonb(v) if k in _JSON_COLUMNS and v is not None else v) for k, v in d.items()}


async def create_project_settings(index_settings: ProjectSettings, admin_email: str | None = None):
    """
    Register a project in the projects table, and optionally assign an admin role to a user.
    """
    values = _values(index_settings, exclude_none=True)
    columns = ["id", *values.keys()]
    placeholders = ", ".join(["%s"] * len(columns))
    await execute(
        f"INSERT INTO projects ({', '.join(columns)}) VALUES ({placeholders})",  # type: ignore[arg-type]
        [index_settings.id, *values.values()],
    )
    if admin_email:
        await create_project_role(admin_email, index_settings.id, Roles.ADMIN)


async def update_project_settings(index_settings: ProjectSettings, ignore_missing: bool = False):
    values = _values(index_settings, exclude_none=True)
    if not values:
        return
    assignments = ", ".join(f"{k} = %s" for k in values)
    n = await execute(
        f"UPDATE projects SET {assignments} WHERE id = %s",  # type: ignore[arg-type]
        [*values.values(), index_settings.id],
    )
    if n == 0:
        if not ignore_missing:
            raise NotFoundError(f"Project {index_settings.id} does not exist")
        await create_project_settings(index_settings)


async def set_project_archived(index_id: str, archived) -> None:
    n = await execute("UPDATE projects SET archived = %s WHERE id = %s", [archived, index_id])
    if n == 0:
        raise NotFoundError(f"Project {index_id} does not exist")


async def delete_project_settings(index_id: str, ignore_missing: bool = False):
    """Delete the project (including its fields and documents) and its roles"""
    async with connection() as conn:
        async with conn.transaction():
            cur = await conn.execute("DELETE FROM projects WHERE id = %s", [index_id])
            if cur.rowcount == 0 and not ignore_missing:
                raise NotFoundError(f"Project {index_id} does not exist")
            # roles, requests, fields, documents, jobs and the object storage register are deleted by cascade


async def get_project_image(index_id: IndexId) -> ImageObject | None:
    row = await fetch_one("SELECT image FROM projects WHERE id = %s", [index_id])
    if row is None:
        raise NotFoundError(f"Project {index_id} does not exist")
    if not row["image"]:
        return None
    return ImageObject.model_validate(row["image"])


## SERVER SETTINGS


async def get_server_settings() -> ServerSettings:
    row = await fetch_one("SELECT settings FROM server_settings")
    if row is None:
        return ServerSettings()
    return ServerSettings.model_validate(row["settings"])


async def upsert_server_settings(server_settings: ServerSettings):
    doc = server_settings.model_dump(exclude_none=True, mode="json")
    await execute(
        """INSERT INTO server_settings (id, settings) VALUES (true, %s)
           ON CONFLICT (id) DO UPDATE SET settings = server_settings.settings || EXCLUDED.settings""",
        [Jsonb(doc)],
    )
