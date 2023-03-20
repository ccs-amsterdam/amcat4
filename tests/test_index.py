from typing import List

import pytest

from amcat4.config import get_settings
from amcat4.elastic import es
from amcat4.index import (Role, create_index, delete_index, deregister_index,
                          get_global_role, get_guest_role, get_index, get_role,
                          list_global_users, list_known_indices, list_users,
                          modify_index, refresh_index, register_index,
                          remove_global_role, remove_role, set_global_role,
                          set_guest_role, set_role)
from tests.tools import refresh


def list_es_indices() -> List[str]:
    """
    List all indices on the connected elastic cluster.
    """
    return list(es().indices.get(index="*").keys())


def list_index_names(email: str = None) -> List[str]:
    return [ix.name for ix in list_known_indices(email)]


def test_create_delete_index():
    # Can we create and delete indices?
    index = "amcat4_unittest"
    delete_index(index, ignore_missing=True)
    refresh_index(get_settings().system_index)
    assert index not in list_es_indices()
    assert index not in list_index_names()
    create_index(index)
    refresh_index(get_settings().system_index)
    assert index in list_es_indices()
    assert index in list_index_names()
    # Cannot create or register duplicate index
    with pytest.raises(Exception):
        create_index(index.name)
    with pytest.raises(Exception):
        register_index(index.name)
    delete_index(index)
    refresh_index(get_settings().system_index)
    assert index not in list_es_indices()
    assert index not in list_index_names()


def test_register_index():
    index = "amcat4_unittest"
    delete_index(index, ignore_missing=True)
    es().indices.create(index=index)
    assert index in list_es_indices()
    assert index not in list_index_names()
    register_index(index)
    refresh_index(get_settings().system_index)
    assert index in list_index_names()
    deregister_index(index)
    refresh_index(get_settings().system_index)
    assert index not in list_index_names()


def test_list_indices(index, guest_index, admin):
    assert index in list_index_names()
    assert guest_index in list_index_names()
    assert index in list_index_names(admin)
    assert guest_index in list_index_names(admin)
    user = "user@example.com"
    assert index not in list_index_names(user)
    assert guest_index in list_index_names(user)
    set_role(index, user, Role.WRITER)
    refresh_index(get_settings().system_index)
    assert index in list_index_names(user)
    remove_role(index, user)
    refresh_index(get_settings().system_index)
    assert index not in list_index_names(user)


def test_global_roles():
    user = "user@example.com"
    assert get_global_role(user) is None
    set_global_role(user, Role.ADMIN)
    refresh_index(get_settings().system_index)
    assert get_global_role(user) == Role.ADMIN
    set_global_role(user, Role.WRITER)
    refresh_index(get_settings().system_index)
    assert get_global_role(user) == Role.WRITER
    remove_global_role(user)
    refresh_index(get_settings().system_index)
    assert get_global_role(user) is None


def test_index_roles(index):
    user = "user@example.com"
    assert get_role(index, user) is None
    set_role(index, user, Role.METAREADER)
    refresh_index(get_settings().system_index)
    assert get_role(index, user) == Role.METAREADER
    set_role(index, user, Role.ADMIN)
    refresh_index(get_settings().system_index)
    assert get_role(index, user) == Role.ADMIN
    remove_role(index, user)
    refresh_index(get_settings().system_index)
    assert get_role(index, user) is None


def test_guest_role(index):
    assert get_guest_role(index) is None
    set_guest_role(index, Role.READER)
    refresh()
    assert get_guest_role(index) == Role.READER


def test_builtin_admin(index):
    user = "admin@example.com"
    get_settings().admin_email = user
    assert get_global_role(user) == Role.ADMIN
    assert index in list_index_names(user)


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
    indices = {x.id: x for x in list_known_indices()}
    assert indices[index].name == "test"
