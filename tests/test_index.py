import pytest

from amcat4 import elastic
from amcat4.auth import Role
from amcat4.index import create_index


def test_create_index(index):
    assert elastic.index_exists(index.name) is True
    assert index.name in elastic._list_indices()
    with pytest.raises(Exception):
        create_index(index.name, create_in_elastic=True)  # can't create duplicate index
    with pytest.raises(Exception):
        create_index(index.name, create_in_elastic=False)  # can't create duplicate index

    # De-register the index. It should still exist in elastic, so we can't re-create it
    index.delete_index(delete_from_elastic=False)
    assert elastic.index_exists(index.name) is True
    with pytest.raises(Exception):
        create_index(index.name, create_in_elastic=True)  # can't create duplicate index

    # Re-register the index and delete it. It should now be really gone
    ix = create_index(index.name, create_in_elastic=False)
    ix.delete_index(delete_from_elastic=True)
    assert elastic.index_exists(index.name) is False
    with pytest.raises(Exception):
        create_index(index.name, create_in_elastic=False)
    assert index.name not in elastic._list_indices()


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
