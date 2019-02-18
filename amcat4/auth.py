"""
Provide authentication for AmCAT4 api

Currently provides token based authentication using an elasticsearch backend,
assuming a 'amcat4system' index
"""
import logging
from secrets import token_hex

import bcrypt
from peewee import Model, CharField, BooleanField
from amcat4.db import db


class User(Model):
    email = CharField(unique=True)
    password = CharField()
    is_admin = BooleanField(default=False)
    is_creator = BooleanField(default=False)

    class Meta:
        database = db

    def create_token(self) -> str:
        """
        Create a new token for this user
        """
        token = token_hex(8)
        es.create(SYS_INDEX, SYS_MAPPING, token, {'email': self.email, 'type': 'token'})
        return token


def create_user(email: str, password: str, is_admin: bool = False, is_creator: bool = False) -> User:
    """
    Create and return a new User with the given information
    """
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    return User.create(email=email, password=hashed, is_admin=is_admin, is_creator=is_creator)


def verify_user(email: str, password: str) -> User:
    """
    Check that this user exists and can be authenticated with the given password, returning a User object
    :param email: Email address identifying the user
    :param password: Password to check
    :return: A User object if user could be authenticated, None otherwise
    """
    logging.info("Attempted login: {email}".format(**locals()))
    try:
        user = User.get(User.email == email)
    except User.DoesNotExist:
        logging.warning("User {email} not found!".format(**locals()))
        return None
    if bcrypt.checkpw(password.encode('utf-8'), user.password.encode("utf-8")):
        return user
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
