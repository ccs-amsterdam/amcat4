"""
Provide authentication for AmCAT4 api

Currently provides token based authentication using an elasticsearch backend,
assuming a 'amcat4system' index
"""
import logging
from secrets import token_hex

import bcrypt
from elasticsearch import NotFoundError
from amcat4.elastic import es, SYS_INDEX, SYS_MAPPING

SECRET_KEY = 'geheim'

ROLE_ADMIN = "admin"  # Can do anything
ROLE_CREATOR = "creator"  # Can create projects


def role_set(str_or_sequence):
    if str_or_sequence is None:
        return set()
    if isinstance(str_or_sequence, str):
        return {str_or_sequence}
    else:
        return set(str_or_sequence)


class User:
    def __init__(self, email, roles):
        self.email = email
        self.roles = role_set(roles)

    def has_role(self, role):
        return bool(self.roles & {ROLE_ADMIN, role})

    def create_token(self) -> str:
        """
        Create a new token for this user
        """
        token = token_hex(8)
        es.create(SYS_INDEX, SYS_MAPPING, token, {'email': self.email, 'type': 'token'})
        return token

    def delete(self, ignore_missing=False):
        """
        Delete the user
        :param email: Email address identifying the user
        :param ignore_missing: If False (default), throw an exception if user does not exist
        """
        es.delete(SYS_INDEX, SYS_MAPPING, self.email, ignore=([404] if ignore_missing else []))

    def __eq__(self, other):
        return self.email == other.email


def has_user() -> bool:
    """
    Is there at least one user?
    """
    es.indices.flush()
    res = es.count(SYS_INDEX, SYS_MAPPING, body={"query": {"match": {"type": "user"}}})
    return res['count'] > 0


def create_user(email: str, password: str, roles=None) -> User:
    """
    Create a new user on this server
    :param email: Email address identifying the user
    :param password: New password
    :param roles: Roles for this user, see ROLE_* module variables
    :param check_email: if True (default), raise an error for invalid email addresses
    """
    if es.exists(SYS_INDEX, SYS_MAPPING, id=email):
        raise ValueError("User {email} already exists".format(**locals()))
    hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    es.create(SYS_INDEX, SYS_MAPPING, email, {'hash': hash, 'roles': roles, 'type': 'user'})
    return User(email, roles)


def verify_user(email: str, password: str) -> User:
    """
    Check that this user exists and is authenticated with the given password
    :param email: Email address identifying the user
    :param password: Password to check
    :return: A User object if user could be authenticated, None otherwise
    """
    logging.info("Attempted login: {email}".format(**locals()))
    try:
        user = es.get(SYS_INDEX, SYS_MAPPING, email)
    except NotFoundError:
        logging.warning("User {email} not found!".format(**locals()))
        return None
    if bcrypt.checkpw(password.encode('utf-8'), user['_source']['hash'].encode("utf-8")):
        return User(email, user['_source']['roles'])
    else:
        logging.warning("Incorrect password for user {email}".format(**locals()))


def verify_token(token: str) -> User:
    """
    Check the token and return the authenticated user email
    :param token: The token to verify
    :return: a User object if user could be authenticated, None otherwise
    """
    try:
        result = es.get(SYS_INDEX, SYS_MAPPING, token)
    except NotFoundError:
        return None
    email = result['_source']['email']
    u = es.get(SYS_INDEX, SYS_MAPPING, email)
    return User(email, u['_source']['roles'])


def delete_token(token: str, ignore_missing=False):
    """
    Delete the given token
    :param token: The token to delete
    :param ignore_missing: If False (default), throw an exception if token does not exist
    """
    es.delete(SYS_INDEX, SYS_MAPPING, token, ignore=([404] if ignore_missing else []))
