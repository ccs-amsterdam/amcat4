import pytest

from amcat4.index import create_index, list_all_indices, list_known_indices, delete_index, refresh, register_index, \
    deregister_index, get_role, set_role, remove_role, Role, get_global_role, remove_global_role, set_global_role
from amcat4.elastic import es


def test_create_delete_index():
    index = "amcat4_unittest"
    delete_index(index, ignore_missing=True)
    assert index not in list_all_indices()
    assert index not in list_known_indices()
    create_index(index)
    assert index in list_all_indices()
    assert index in list_known_indices()
    # Cannot create or register duplicate index
    with pytest.raises(Exception):
        create_index(index.name)
    with pytest.raises(Exception):
        register_index(index.name)
    delete_index(index)
    assert index not in list_all_indices()
    assert index not in list_known_indices()


def test_register_index():
    index = "amcat4_unittest"
    delete_index(index, ignore_missing=True)
    es().indices.create(index=index)
    assert index in list_all_indices()
    assert index not in list_known_indices()
    register_index(index)
    assert index in list_known_indices()
    deregister_index(index)
    assert index not in list_known_indices()


def test_list_indices(index, guest_index, admin):
    assert index in list_known_indices()
    assert guest_index in list_known_indices()
    assert index in list_known_indices(admin)
    assert guest_index in list_known_indices(admin)
    user = "user@example.com"
    assert index not in list_known_indices(user)
    assert guest_index in list_known_indices(user)


def test_global_roles():
    user = "user@example.com"
    assert get_global_role(user) is None
    set_global_role(user, Role.ADMIN)
    assert get_global_role(user) == Role.ADMIN
    set_global_role(user, Role.WRITER)
    assert get_global_role(user) == Role.WRITER
    remove_global_role(user)
    assert get_global_role(user) is None


def test_index_roles(index):
    user = "user@example.com"
    assert get_role(index, user) is None
    set_role(index, user, Role.METAREADER)
    assert get_role(index, user) == Role.METAREADER
    set_role(index, user, Role.ADMIN)
    assert get_role(index, user) == Role.ADMIN
    remove_role(index, user)
    assert get_role(index, user) is None
