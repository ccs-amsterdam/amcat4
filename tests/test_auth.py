import random
import string

from nose.tools import assert_is_not_none, assert_equals

from amcat4.auth import verify_user, create_user, ROLE_CREATOR, verify_token, delete_token


def test_create_check_user():
    name = ''.join(random.choices(string.ascii_lowercase, k=32))
    email = "{}@example.org".format(name)
    password = name
    assert not verify_user(email, password)
    u = create_user(email, password, roles=ROLE_CREATOR)
    try:
        u2 = verify_user(email, password)
        assert_is_not_none(u2, "User could not be found")
        assert_equals(u2.roles, {ROLE_CREATOR})
        assert not verify_user(email, "fout")
        u2.delete()
        assert not verify_user(email, password)
    finally:
        u.delete(ignore_missing=True)


def test_token():
    name = ''.join(random.choices(string.ascii_lowercase, k=32))
    email = "{}@example.org".format(name)
    u = create_user(email, 'password')
    token = u.create_token()
    try:
        assert verify_token(token).email == u.email
        delete_token(token)
        assert verify_token(token) is None
    finally:
        delete_token(token, ignore_missing=True)
