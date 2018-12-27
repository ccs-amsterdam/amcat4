import random
import string

from amcat4.auth import verify_user, create_user, ROLE_CREATOR, delete_user, create_token, verify_token, delete_token


def test_create_check_user():
    name = ''.join(random.choices(string.ascii_lowercase, k=32))
    email = "{}@example.org".format(name)
    password = name
    assert not verify_user(email, password)
    create_user(email, password, roles=ROLE_CREATOR)
    try:
        assert verify_user(email, password)
        assert not verify_user(email, "fout")
        delete_user(email)
        assert not verify_user(email, password)
    finally:
        delete_user(email, ignore_missing=True)

def test_token():
    name = ''.join(random.choices(string.ascii_lowercase, k=32))
    email = "{}@example.org".format(name)
    token = create_token(email)
    try:
        assert verify_token(token) == email
        delete_token(token)
        assert verify_token(token) is None
    finally:
        delete_token(token, ignore_missing=True)
