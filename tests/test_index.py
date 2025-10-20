from typing import List

import pytest

from amcat4.config import get_settings
from amcat4.elastic import es
from amcat4.models import ProjectSettings, Roles, User
from amcat4.projects.index import (
    create_project_index,
    delete_project_index,
    deregister_project_index,
    list_project_indices,
    list_user_project_indices,
    register_project_index,
)
from amcat4.systemdata.roles import (
    delete_project_role,
    delete_server_role,
    get_project_guest_role,
    get_user_project_role,
    get_user_server_role,
    list_project_roles,
    list_server_roles,
    set_project_guest_role,
    update_project_role,
    update_server_role,
)
from amcat4.systemdata.settings import get_project_settings, update_project_settings

## TODO: replace all the functions from the removed amcat4.index with the new functions


def list_es_indices() -> List[str]:
    """
    List all indices on the connected elastic cluster.
    """
    return list(es().indices.get(index="*").keys())


def list_index_ids(email: str | None = None) -> List[str]:
    if email is None:
        return [ix.id for ix in list_project_indices()]
    else:
        return [ix.id for ix, role in list_user_project_indices(User(email=email))]


def test_create_delete_project_index():
    # Can we create and delete indices?
    index = "amcat4_unittest"
    delete_project_index(index, ignore_missing=True)
    # refresh_index(get_settings().system_index)   # I'm trying to get rid of these; should not be necessary
    assert index not in list_es_indices()
    assert index not in list_index_ids()
    create_project_index(ProjectSettings(id=index))
    # refresh_index(get_settings().system_index)
    assert index in list_es_indices()
    assert index in list_index_ids()
    # Cannot create duplicate index
    with pytest.raises(Exception):
        create_project_index(ProjectSettings(id=index))
    delete_project_index(index)
    # refresh_index(get_settings().system_index)
    assert index not in list_es_indices()
    assert index not in list_index_ids()


def test_import_index():
    # To import an existing es index, we create the index settings
    index = "amcat4_unittest"
    delete_project_index(index, ignore_missing=True)
    es().indices.create(index=index)
    assert index in list_es_indices()
    assert index not in list_index_ids()
    register_project_index(ProjectSettings(id=index))
    # refresh_index(get_settings().system_index)
    assert index in list_index_ids()
    deregister_project_index(index)
    # refresh_index(get_settings().system_index)
    assert index not in list_index_ids()


def test_list_indices(index, guest_index, admin):
    assert index in list_index_ids()
    assert guest_index in list_index_ids()
    assert index in list_index_ids(admin)
    assert guest_index in list_index_ids(admin)
    user = "user@example.com"
    assert index not in list_index_ids(user)
    assert guest_index in list_index_ids(user)
    update_project_role(user, index, Roles.WRITER)
    # refresh_index(get_settings().system_index)
    assert index in list_user_project_indices(User(email=user))
    delete_project_index(index)
    # refresh_index(get_settings().system_index)
    assert index not in list_user_project_indices(User(email=user))


def test_global_roles():
    email = "user@example.com"
    user = User(email=email)
    assert get_user_server_role(user).role == Roles.NONE.name
    update_server_role(email_pattern=email, role=Roles.ADMIN)
    # refresh_index(get_settings().system_index)
    assert get_user_server_role(user).role == Roles.ADMIN.name
    update_server_role(email_pattern=email, role=Roles.WRITER)
    # refresh_index(get_settings().system_index)
    assert get_user_server_role(user).role == Roles.WRITER.name
    delete_server_role(email_pattern=email)
    # refresh_index(get_settings().system_index)
    assert get_user_server_role(user).role == Roles.NONE.name


def test_index_roles(index):
    email = "user@example.com"
    user = User(email=email)
    assert get_user_project_role(user, index).role == Roles.NONE
    update_project_role(email_pattern=email, project_id=index, role=Roles.WRITER)
    # refresh_index(get_settings().system_index)
    assert get_user_project_role(user, index).role == Roles.METAREADER
    update_project_role(email_pattern=email, project_id=index, role=Roles.ADMIN)
    # refresh_index(get_settings().system_index)
    assert get_user_project_role(user, index).role == Roles.ADMIN
    delete_project_role(email_pattern=email, project_id=index)
    # refresh_index(get_settings().system_index)
    assert get_user_project_role(user, index).role == Roles.NONE


def test_guest_role(index):
    assert get_project_guest_role(index) == Roles.NONE.name
    set_project_guest_role(index, Roles.READER)
    # refresh()
    assert get_project_guest_role(index) == Roles.READER.name


def test_builtin_admin(index):
    user = "admin@example.com"
    get_settings().admin_email = user
    assert get_user_server_role(User(email=user)).role == Roles.ADMIN.name
    assert index in list_index_ids(user)


def test_list_users(index, user):
    update_server_role(user, role=Roles.WRITER)
    # refresh_index(get_settings().system_index)
    project_users = list_project_roles()
    server_users = list_server_roles()

    assert len(list(server_users)) > 0
    assert len(list(project_users)) > 0


def test_name_description(index):
    update_project_settings(ProjectSettings(id=index, name="test", description="ooktest"))
    # refresh()
    assert get_project_settings(index).name == "test"
    assert get_project_settings(index).description == "ooktest"
    indices = {x.id: x for x in list_project_indices()}
    assert indices[index].name == "test"


# def test_summary_field(index):
#     with pytest.raises(Exception):
#         modify_index(index, summary_field="doesnotexist")
#     with pytest.raises(Exception):
#         modify_index(index, summary_field="title")
#     update_fields(index, {"party": Field(type="keyword", type="keyword")})
#     modify_index(index, summary_field="party")
#     assert get_index(index).summary_field == "party"
#     modify_index(index, summary_field="date")
#     assert get_index(index).summary_field == "date"
