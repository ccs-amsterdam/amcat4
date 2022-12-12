import pytest

from amcat4 import elastic
from amcat4.auth import Role
from amcat4.index import create_index, list_all_indices, list_known_indices, delete_index, refresh, register_index, \
    deregister_index
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


def test_roles(index, guest_index, user, admin):
    def test(ix, u, expected_roles):
        actual_roles = {role for role in Role if ix.has_role(u, role)}
        assert expected_roles == actual_roles

    # Index should not be visible to the user
    assert index not in user.indices(include_guest=True)
    test(index, user, set())
    test(index, admin, set())

    # Give user a role, index should now be visible
    index.set_role(user, Role.METAREADER)
    assert Role.METAREADER == user.indices()[index]
    test(index, user, {Role.METAREADER})
    test(index, admin, set())
    index.set_role(user, Role.READER)
    test(index, user, {Role.METAREADER, Role.READER})

    guest_index.set_role(admin, Role.ADMIN)

    assert guest_index not in user.indices(include_guest=False)
    assert user.indices(include_guest=True)[guest_index] == Role.READER
    assert admin.indices(include_guest=True)[guest_index] == Role.ADMIN
    assert admin.indices(include_guest=False)[guest_index] == Role.ADMIN

    test(guest_index, user, {Role.METAREADER, Role.READER})
    test(guest_index, admin, {Role.METAREADER, Role.READER, Role.WRITER, Role.ADMIN})


def test_list_users(index, user):
    assert {u.email: r.name for (u, r) in index.get_roles()} == {}
    index.set_role(user, Role.READER)
    assert {u.email: r.name for (u, r) in index.get_roles()} == {user.email: "READER"}
