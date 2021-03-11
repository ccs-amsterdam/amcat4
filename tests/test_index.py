import random
import string

from nose.tools import assert_is_not_none, assert_equals, assert_false, assert_true, assert_is_none, assert_raises, \
    assert_not_in

from amcat4 import index, elastic
from amcat4.auth import create_user, Role, User
from tests.tools import with_index


def test_create_index():
    name = "amcat4_test__" + ''.join(random.choices(string.ascii_lowercase, k=16))
    # Index should not exist, and we can't register (ie create in amcat4 but not in elastic) non-existing indices
    assert_false(elastic.index_exists(name))
    assert_raises(Exception, index.create_index, name, create_in_elastic=False)  # can't register non-existing index

    # Create the index
    ix = index.create_index(name)
    try:
        # Now it should exist, so we can't create it again
        assert_true(elastic.index_exists(name))
        assert_raises(Exception, index.create_index, name, create_in_elastic=True)  # can't create duplicate index
        assert_raises(Exception, index.create_index, name, create_in_elastic=False)  # can't create duplicate index

        # De-register the index. It should still exist in elastic, so we can't re-create it
        ix.delete_index(delete_from_elastic=False)
        assert_true(elastic.index_exists(name))
        assert_raises(Exception, index.create_index, name, create_in_elastic=True)  # can't create duplicate index

        # Re-register the index and delete it. It should now be really gone
        ix = index.create_index(name, create_in_elastic=False)
        ix.delete_index(delete_from_elastic=True)
        assert_false(elastic.index_exists(name))
    finally:
        elastic._delete_index(name, ignore_missing=True)


@with_index
def test_roles(index_name):
    user_admin = create_user("admin", "admin", Role.ADMIN)
    user_noob = create_user("noob", "admin", None)
    ix = index.create_index(index_name, guest_role=None, admin=None, create_in_elastic=False)

    def test(u, roles):
        for role in Role:
            should_have = role in roles
            assert_equals(ix.has_role(u, role), should_have,
                          "User {} should {}have role {!r}".format(u.email, "" if should_have else "not ", role.name))

    # Index should not be visible to the user
    assert_not_in(ix, user_noob.indices(include_guest=True))
    test(user_noob, [])
    test(user_admin, [])

    # Give user a role, index should now be visible
    ix.set_role(user_noob, Role.METAREADER)
    assert_equals(Role.METAREADER, user_noob.indices(include_guest=False)[ix])
    assert_equals(Role.METAREADER, user_noob.indices(include_guest=True)[ix])
    test(user_noob, {Role.METAREADER})
    test(user_admin, [])
    ix.set_role(user_noob, Role.READER)
    test(user_noob, {Role.METAREADER, Role.READER})

    # Delete index
    ix.delete_index(delete_from_elastic=False)
    test(user_noob, [])
    test(user_admin, [])

    # Recreate index with gues role and admin.
    ix = index.create_index(index_name, guest_role=Role.READER, admin=user_admin, create_in_elastic=False)
    try:
        assert_not_in(ix, user_noob.indices(include_guest=False))
        assert_equals(Role.READER, user_noob.indices(include_guest=True)[ix])
        assert_equals(Role.ADMIN, user_admin.indices(include_guest=False)[ix])
        assert_equals(Role.ADMIN, user_admin.indices(include_guest=True)[ix])
        test(user_noob, [Role.METAREADER, Role.READER])
        test(user_admin, [Role.METAREADER, Role.READER, Role.WRITER, Role.ADMIN])
    finally:
        ix.delete_index()




