import random
import string

from nose.tools import assert_is_not_none, assert_equals, assert_false, assert_true, assert_is_none

from amcat4.auth import verify_user, create_user, verify_token


def test_create_check_user():
    name = ''.join(random.choices(string.ascii_lowercase, k=32))
    email = "{}@example.org".format(name)
    password = name
    assert_is_none(verify_user(email, password))
    u = create_user(email, password, is_creator=True)
    try:
        u2 = verify_user(email, password)
        assert_is_not_none(u2, "User could not be found")
        assert_true(u2.is_creator)
        assert_false(u2.is_admin)
        assert_is_none(verify_user(email, "fout"))
        u.delete_instance()
        assert_is_none(verify_user(email, password))
    finally:
        u.delete_instance()


def test_token():
    assert_is_none(verify_token("invalid"))
    name = ''.join(random.choices(string.ascii_lowercase, k=32))
    email = "{}@example.org".format(name)
    u = create_user(email, 'password')
    token = u.create_token()
    assert_equals(verify_token(token).email, u.email)
