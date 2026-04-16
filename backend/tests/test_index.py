from typing import List

import pytest

from amcat4.connections import es
from amcat4.models import ProjectSettings, Roles, User
from amcat4.projects.index import (
    clear_project_index,
    create_project_index,
    delete_project_index,
    deregister_project_index,
    list_project_indices,
    list_user_project_indices,
    register_project_index,
)
from amcat4.systemdata.fields import list_fields
from amcat4.systemdata.roles import (
    create_project_role,
    create_server_role,
    delete_project_role,
    delete_server_role,
    get_project_guest_role,
    get_user_project_role,
    get_user_server_role,
    list_project_roles,
    set_project_guest_role,
    update_project_role,
    update_server_role,
)
from amcat4.systemdata.settings import get_project_settings, update_project_settings


async def list_es_indices() -> List[str]:
    """
    List all indices on the connected elastic cluster.
    """
    return list((await es().indices.get(index="*")).keys())


async def list_index_ids(email: str | None = None) -> List[str]:
    if email is None:
        return [ix.id async for ix in list_project_indices()]
    else:
        return [ix.id async for ix, role in list_user_project_indices(User(email=email))]


@pytest.mark.anyio
async def test_create_delete_project_index():
    # Can we create and delete indices?
    index = "amcat4_unittest"
    await delete_project_index(index, ignore_missing=True)
    assert index not in await list_es_indices()
    assert index not in await list_index_ids()
    await create_project_index(ProjectSettings(id=index))
    assert index in await list_es_indices()
    assert index in await list_index_ids()
    # Cannot create duplicate index
    with pytest.raises(Exception):
        await create_project_index(ProjectSettings(id=index))
    await delete_project_index(index)
    assert index not in await list_es_indices()
    assert index not in await list_index_ids()


@pytest.mark.anyio
async def test_import_index():
    # To import an existing es index, we create the index settings
    index = "amcat4_unittest"
    await delete_project_index(index, ignore_missing=True)
    await es().indices.create(index=index)
    assert index in await list_es_indices()
    assert index not in await list_index_ids()
    await register_project_index(ProjectSettings(id=index))
    assert index in await list_index_ids()
    await deregister_project_index(index)
    assert index not in await list_index_ids()


@pytest.mark.anyio
async def test_global_roles():
    email = "user@example.com"
    user = User(email=email)
    assert (await get_user_server_role(user)).role == Roles.NONE.name
    await create_server_role(email=email, role=Roles.ADMIN)
    assert (await get_user_server_role(user)).role == Roles.ADMIN.name
    await update_server_role(email=email, role=Roles.WRITER)
    assert (await get_user_server_role(user)).role == Roles.WRITER.name
    await delete_server_role(email=email)
    assert (await get_user_server_role(user)).role == Roles.NONE.name


@pytest.mark.anyio
async def test_index_roles(index):
    email = "user@example.com"
    user = User(email=email)
    assert (await get_user_project_role(user, index)).role == Roles.NONE.name
    await create_project_role(email=email, project_id=index, role=Roles.WRITER)
    assert (await get_user_project_role(user, index)).role == Roles.WRITER.name
    await update_project_role(email=email, project_id=index, role=Roles.ADMIN)
    assert (await get_user_project_role(user, index)).role == Roles.ADMIN.name
    await delete_project_role(email=email, project_id=index)
    assert (await get_user_project_role(user, index)).role == Roles.NONE.name


@pytest.mark.anyio
async def test_guest_role(index):
    assert await get_project_guest_role(index) == Roles.NONE.name
    await set_project_guest_role(index, Roles.READER)
    # await refresh()
    assert await get_project_guest_role(index) == Roles.READER.name


@pytest.mark.anyio
async def test_superadmin(index):
    """
    The User object passed by the authenticate_user dependency can
    identify a user as superadmin. This is the case if the user's email
    matches the admin_email setting, or when auth is disabled.
    A superadmin has ADMIN role everywhere
    """
    superadmin = User(email="doesnt@matter.com", superadmin=True)
    assert (await get_user_server_role(superadmin)).role == Roles.ADMIN.name
    assert (await get_user_project_role(superadmin, index)).role == Roles.ADMIN.name


@pytest.mark.anyio
async def test_list_users(index, user):
    await create_project_role("user@domain.com", index, role=Roles.READER)
    await create_project_role("*@domain.com", index, role=Roles.METAREADER)
    project_users = list_project_roles()
    assert len([p async for p in project_users]) == 2


@pytest.mark.anyio
async def test_name_description(index):
    await update_project_settings(ProjectSettings(id=index, name="test", description="ooktest"))
    # await refresh()
    assert (await get_project_settings(index)).name == "test"
    assert (await get_project_settings(index)).description == "ooktest"
    indices = {x.id: x async for x in list_project_indices()}
    assert indices[index].name == "test"


@pytest.mark.anyio
async def test_clear_project_index(index_docs):
    """Clearing a project should remove documents and fields but preserve settings and roles."""
    index = index_docs
    admin_email = "admin@test.nl"
    await create_project_role(admin_email, index, Roles.ADMIN)

    # Verify preconditions: documents and fields exist
    doc_count = (await es().count(index=index))["count"]
    assert doc_count > 0
    fields = await list_fields(index, auto_repair=False)
    assert len(fields) > 0
    settings = await get_project_settings(index)
    assert settings.id == index

    # Clear the project
    await clear_project_index(index)

    # ES index still exists but is empty
    assert await es().indices.exists(index=index)
    doc_count = (await es().count(index=index))["count"]
    assert doc_count == 0

    # Mapping is reset to empty
    mapping = await es().indices.get_mapping(index=index)
    assert mapping[index]["mappings"].get("properties", {}) == {}

    # Field definitions are gone from system index
    fields = await list_fields(index, auto_repair=False)
    assert len(fields) == 0

    # Settings and roles are preserved
    settings = await get_project_settings(index)
    assert settings.id == index
    role = await get_user_project_role(User(email=admin_email), index)
    assert role.role == Roles.ADMIN.name
