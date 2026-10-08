import logging
from datetime import UTC, datetime
from typing import AsyncIterable

from botocore.exceptions import BotoCoreError

from amcat4.connections import s3_enabled
from amcat4.errors import NotFoundError
from amcat4.models import IndexId, ProjectSettings, RoleRule, Roles, User
from amcat4.objectstorage.multimedia import delete_project_multimedia
from amcat4.postgres.connection import connection, fetch_all, fetch_one
from amcat4.systemdata.roles import list_user_project_roles
from amcat4.systemdata.settings import (
    _project_from_row,
    create_project_settings,
    delete_project_settings,
    get_project_settings,
    set_project_archived,
    update_project_settings,
)


class IndexDoesNotExist(ValueError):
    pass


class IndexAlreadyExists(ValueError):
    pass


async def create_project_index(new_index: ProjectSettings, admin_email: str | None = None):
    """
    Create a new project, optionally with an admin user
    """
    if await fetch_one("SELECT 1 FROM projects WHERE id = %s", [new_index.id]):
        raise IndexAlreadyExists(f'Project "{new_index.id}" already exists')
    await create_project_settings(new_index, admin_email)


async def update_project_index(update_index: ProjectSettings):
    """
    Update index settings
    """
    await update_project_settings(update_index)


async def archive_project_index(index_id: str, archived: bool):
    try:
        d = await get_project_settings(index_id)
    except NotFoundError:
        raise IndexDoesNotExist(f"Project {index_id} does not exist")
    if d.archived is not None and archived:
        return
    await set_project_archived(index_id, datetime.now(UTC) if archived else None)


async def clear_project_index(index_id: str):
    """
    Clear all documents and fields from a project, keeping settings and roles intact.
    """
    row = await fetch_one("SELECT pk FROM projects WHERE id = %s", [index_id])
    if row is None:
        raise IndexDoesNotExist(f"Project {index_id} does not exist")
    if s3_enabled():
        try:
            await delete_project_multimedia(index_id)
        except BotoCoreError as e:
            logging.warning(f"Could not delete multimedia for index {index_id}: {e}")
    async with connection() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM documents WHERE project_pk = %s", [row["pk"]])
            await conn.execute("DELETE FROM fields WHERE project_pk = %s", [row["pk"]])


async def delete_project_index(index_id: str, ignore_missing: bool = False):
    """
    Delete the project, including its documents, fields, roles and multimedia
    """
    if s3_enabled():
        try:
            await delete_project_multimedia(index_id)
        except BotoCoreError as e:
            logging.warning(f"Could not delete multimedia for index {index_id}: {e}")
    try:
        await delete_project_settings(index_id, ignore_missing)
    except NotFoundError:
        raise IndexDoesNotExist(f"Project {index_id} does not exist")


async def list_project_indices(ids: list[str] | None = None, skip_archived: bool = True) -> AsyncIterable[ProjectSettings]:
    """
    List all projects, or only those with the given ids.
    """
    conditions, params = ["TRUE"], []
    if ids is not None:
        conditions.append("id = ANY(%s)")
        params.append(ids)
    if skip_archived:
        conditions.append("archived IS NULL")
    rows = await fetch_all(f"SELECT * FROM projects WHERE {' AND '.join(conditions)} ORDER BY id", params)  # type: ignore[arg-type]
    for row in rows:
        yield _project_from_row(row)


async def list_user_project_indices(
    user: User, show_all=False, show_archived=False
) -> AsyncIterable[tuple[ProjectSettings, RoleRule | None]]:
    """
    List all indices that a user has any role on.
    Return both the index and RoleRule that the user matched for that index (can be None if show_all is True)
    """
    if show_all:
        ## ONLY ALLOWED FOR SERVER ADMINS. make sure to check role before setting this param
        async for index in list_project_indices(skip_archived=not show_archived):
            yield index, RoleRule(role=Roles.ADMIN.name, role_context=index.id, email=user.email or "*")
        return

    project_role_lookup: dict[str, RoleRule] = {}
    roles = await list_user_project_roles(user, required_role=Roles.OBSERVER)
    for role in roles:
        project_role_lookup[role.role_context] = role

    async for index in list_project_indices(ids=list(project_role_lookup.keys()), skip_archived=not show_archived):
        yield index, project_role_lookup[index.id]


async def index_size_in_bytes(index_id: IndexId) -> int:
    """(Approximate) size of the documents of the project, as stored on disk (after compression)"""
    row = await fetch_one(
        """SELECT coalesce(sum(pg_column_size(d.*)), 0) AS bytes FROM documents d
           WHERE d.project_pk = (SELECT pk FROM projects WHERE id = %s)""",
        [index_id],
    )
    return int(row["bytes"]) if row else 0
