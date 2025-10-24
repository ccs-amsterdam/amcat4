from typing import List

import pytest

from amcat4.api.auth import authenticated_user
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
    create_project_role,
    create_server_role,
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
    assert index not in list_es_indices()
    assert index not in list_index_ids()
    create_project_index(ProjectSettings(id=index))
    assert index in list_es_indices()
    assert index in list_index_ids()
    # Cannot create duplicate index
    with pytest.raises(Exception):
        create_project_index(ProjectSettings(id=index))
    delete_project_index(index)
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
    assert index in list_index_ids()
    deregister_project_index(index)
    assert index not in list_index_ids()


def test_global_roles():
    email = "user@example.com"
    user = User(email=email)
    assert get_user_server_role(user).role == Roles.NONE.name
    create_server_role(email=email, role=Roles.ADMIN)
    assert get_user_server_role(user).role == Roles.ADMIN.name
    update_server_role(email=email, role=Roles.WRITER)
    assert get_user_server_role(user).role == Roles.WRITER.name
    delete_server_role(email=email)
    assert get_user_server_role(user).role == Roles.NONE.name


def test_index_roles(index):
    email = "user@example.com"
    user = User(email=email)
    assert get_user_project_role(user, index).role == Roles.NONE.name
    create_project_role(email=email, project_id=index, role=Roles.WRITER)
    assert get_user_project_role(user, index).role == Roles.WRITER.name
    update_project_role(email=email, project_id=index, role=Roles.ADMIN)
    assert get_user_project_role(user, index).role == Roles.ADMIN.name
    delete_project_role(email=email, project_id=index)
    assert get_user_project_role(user, index).role == Roles.NONE.name


def test_guest_role(index):
    assert get_project_guest_role(index) == Roles.NONE.name
    set_project_guest_role(index, Roles.READER)
    # refresh()
    assert get_project_guest_role(index) == Roles.READER.name


def test_superadmin(index):
    """
    The User object passed by the authenticate_user dependency can
    identify a user as superadmin. This is the case if the user's email
    matches the admin_email setting, or when auth is disabled.
    A superadmin has ADMIN role everywhere
    """
    superadmin = User(email="doesnt@matter.com", superadmin=True)
    assert get_user_server_role(superadmin).role == Roles.ADMIN.name
    assert get_user_project_role(superadmin, index).role == Roles.ADMIN.name


def test_list_users(index, user):
    # refresh_index(get_settings().system_index)
    create_project_role("user@domain.com", index, role=Roles.READER)
    create_project_role("*@domain.com", index, role=Roles.METAREADER)
    project_users = list_project_roles()
    assert len(list(project_users)) == 2


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
