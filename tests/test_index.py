import pytest

from amcat4.auth import Role
from amcat4.index import create_index, list_all_indices, list_known_indices, delete_index, refresh, register_index, \
    deregister_index, get_role, set_role, remove_role
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
    assert get_role(user) is None
    set_role(user, Role.ADMIN)
    assert get_role(user) == Role.ADMIN
    set_role(user, Role.WRITER)
    assert get_role(user) == Role.WRITER
    remove_role(user)
    assert get_role(user) is None


def test_index_roles(index):
    user = "user@example.com"
    assert get_role(user, index) is None
    set_role(user, Role.METAREADER, index)
    assert get_role(user, index) == Role.METAREADER
    set_role(user, Role.ADMIN, index)
    assert get_role(user, index) == Role.ADMIN
    remove_role(user, index)
    assert get_role(user, index) is None
