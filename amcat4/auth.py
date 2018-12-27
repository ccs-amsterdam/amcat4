"""
Provide authentication for AmCAT4 api

Currently provides token based authentication using an elasticsearch backend,
assuming a 'amcat4system' index
"""
from secrets import token_hex

import bcrypt
from elasticsearch import NotFoundError
from amcat4.elastic import es, SYS_INDEX, SYS_MAPPING

SECRET_KEY = 'geheim'

ROLE_ADMIN = "admin"  # Can do anything
ROLE_CREATOR = "creator"  # Can create projects


def has_user() -> bool:
    """
    Is there at least one user?
    """
    es.indices.flush()
    res = es.count(SYS_INDEX, SYS_MAPPING, body={"query": {"match": {"type": "user"}}})
    return res['count'] > 0

def create_user(email: str, password: str, roles=None, check_email=True):
    """
    Create a new user on this server
    :param email: Email address identifying the user
    :param password: New password
    :param roles: Roles for this user, see ROLE_* module variables
    :param check_email: if True (default), raise an error for invalid email addresses
    """
    if check_email and "@" not in email:
        # This makes sure there cannot be confusion between user and token entries
        raise ValueError("Invalid email address")
    if es.exists(SYS_INDEX, SYS_MAPPING, id=email):
        raise ValueError("User {email} already exists".format(**locals()))
    hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    es.create(SYS_INDEX, SYS_MAPPING, email, {'hash': hash, 'roles': roles, 'type': 'user'})


def verify_user(email: str, password: str) -> bool:
    """
    Check that this user exists and is authenticated with the given password
    :param email: Email address identifying the user
    :param password: Password to check
    :return: True if user could be authenticated, False otherwise
    """
    try:
        user = es.get(SYS_INDEX, SYS_MAPPING, email)
    except NotFoundError:
        return False
    return bcrypt.checkpw(password.encode('utf-8'), user['_source']['hash'].encode("utf-8"))


def delete_user(email: str, ignore_missing=False):
    """
    Delete the user
    :param email: Email address identifying the user
    :param ignore_missing: If False (default), throw an exception if user does not exist
    """
    es.delete(SYS_INDEX, SYS_MAPPING, email, ignore=([404] if ignore_missing else []))


def create_token(email: str) -> str:
    """
    Create a new token for this user
    :param email: Email address identifying the user
    :return: the created token
    """
    token = token_hex(8)
    es.create(SYS_INDEX, SYS_MAPPING, token, {'email': email, 'type': 'token'})
    return token


def verify_token(token: str) -> str:
    """
    Check the token and return the authenticated user email
    :param token: The token to verify
    :return: the email address identifying the authenticated user
    """
    try:
        result = es.get(SYS_INDEX, SYS_MAPPING, token)
    except NotFoundError:
        return None
    return result['_source']['email']


def delete_token(token: str, ignore_missing=False):
    """
    Delete the given token
    :param token: The token to delete
    :param ignore_missing: If False (default), throw an exception if token does not exist
    """
    es.delete(SYS_INDEX, SYS_MAPPING, token, ignore=([404] if ignore_missing else []))
