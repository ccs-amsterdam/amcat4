from typing import List

import pytest

from amcat4.config import get_settings
from amcat4.elastic import es
from amcat4.models import IndexSettings, User
from amcat4.project_index import (
    create_project_index,
    delete_project_index,
    deregister_project_index,
    list_project_indices,
    list_user_project_indices,
    register_project_index,
)
from amcat4.systemdata.roles import elastic_create_or_update_role
from tests.tools import refresh

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
    create_project_index(IndexSettings(id=index))
    # refresh_index(get_settings().system_index)
    assert index in list_es_indices()
    assert index in list_index_ids()
    # Cannot create duplicate index
    with pytest.raises(Exception):
        create_project_index(IndexSettings(id=index))
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
    register_project_index(IndexSettings(id=index))
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
    elastic_create_or_update_role(index, user, "WRITER")
    refresh_index(get_settings().system_index)
    assert index in list_index_ids(user)
    remove_role(index, user)
    refresh_index(get_settings().system_index)
    assert index not in list_index_ids(user)


def test_global_roles():
    user = "user@example.com"
    assert get_global_role(user) == Role.NONE
    set_global_role(user, Role.ADMIN)
    refresh_index(get_settings().system_index)
    assert get_global_role(user) == Role.ADMIN
    set_global_role(user, Role.WRITER)
    refresh_index(get_settings().system_index)
    assert get_global_role(user) == Role.WRITER
    remove_global_role(user)
    refresh_index(get_settings().system_index)
    assert get_global_role(user) == Role.NONE


def test_index_roles(index):
    user = "user@example.com"
    assert get_role(index, user) == Role.NONE
    set_role(index, user, Role.METAREADER)
    refresh_index(get_settings().system_index)
    assert get_role(index, user) == Role.METAREADER
    set_role(index, user, Role.ADMIN)
    refresh_index(get_settings().system_index)
    assert get_role(index, user) == Role.ADMIN
    remove_role(index, user)
    refresh_index(get_settings().system_index)
    assert get_role(index, user) == Role.NONE


def test_guest_role(index):
    assert get_guest_role(index) == Role.NONE
    set_guest_role(index, GuestRole.READER)
    refresh()
    assert get_guest_role(index) == Role.READER


def test_builtin_admin(index):
    user = "admin@example.com"
    get_settings().admin_email = user
    assert get_global_role(user) == Role.ADMIN
    assert index in list_index_ids(user)


def test_list_users(index, user):
    set_global_role(user, role=Role.WRITER)
    refresh_index(get_settings().system_index)
    assert list_global_users()[user] == Role.WRITER
    remove_global_role(user)
    refresh_index(get_settings().system_index)
    assert user not in list_global_users()

    set_role(index=index, email=user, role=Role.ADMIN)
    refresh_index(get_settings().system_index)
    assert list_users(index)[user] == Role.ADMIN
    remove_role(index=index, email=user)
    refresh_index(get_settings().system_index)
    assert user not in list_users(index)


def test_name_description(index):
    modify_index(index, name="test", description="ooktest")
    refresh()
    assert get_index(index).name == "test"
    assert get_index(index).description == "ooktest"
    indices = {x.id: x for x in list_all_indices()}
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
