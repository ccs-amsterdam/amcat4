import random
import string
from typing import Iterable

from nose.tools import assert_is_not_none, assert_equals, assert_false, assert_true, assert_is_none, assert_set_equal

from amcat4.auth import verify_user, create_user, verify_token, Role
from amcat4.elastic import _delete_index
from amcat4.index import create_index
from tests.tools import assert_set_contains


def test_create_check_user():
    """Can we create a user and verify its password?"""
    name = ''.join(random.choices(string.ascii_lowercase, k=32))
    email = "{}@example.org".format(name)
    password = name
    assert_is_none(verify_user(email, password))
    u = create_user(email, password)
    try:
        u2 = verify_user(email, password)
        assert_is_not_none(u2, "User could not be found")
        assert_is_none(verify_user(email, "fout"))
        u.delete_instance()
        assert_is_none(verify_user(email, password))
    finally:
        u.delete_instance()


def test_token():
    """Can we create a token and verify it?"""
    assert_is_none(verify_token("invalid"))
    name = ''.join(random.choices(string.ascii_lowercase, k=32))
    email = "{}@example.org".format(name)
    u = create_user(email, 'password')
    token = u.create_token()
    assert_equals(verify_token(token).email, u.email)


def test_indices():
    """Does User.indices return the correct results?"""
    name = ''.join(random.choices(string.ascii_lowercase, k=32))
    ix1_name = "amcat4_test__" + ''.join(random.choices(string.ascii_lowercase, k=32))
    ix2_name = "amcat4_test__" + ''.join(random.choices(string.ascii_lowercase, k=32))

    ix1 = create_index(ix1_name)
    ix2 = create_index(ix2_name, guest_role=Role.READER)
    create_index(ix2_name+"x", guest_role=Role.READER)  # make sure other indices don't mess up test
    try:
        email = "{}@example.org".format(name)
        u = create_user(email, 'password')
        assert_equals(set(u.indices(include_guest=False)), set())
        assert_set_contains(u.indices(include_guest=True), {ix2})
        ix1.set_role(u, Role.WRITER)
        assert_equals(set(u.indices(include_guest=False)), {ix1})
        assert_set_contains(u.indices(include_guest=True), {ix1, ix2})
    finally:
        _delete_index(ix1_name, ignore_missing=True)
        _delete_index(ix2_name, ignore_missing=True)


