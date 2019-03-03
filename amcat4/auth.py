"""
Provide authentication for AmCAT4 api

Authentication can work via password or token
See amcat4.index for authorisation rules
"""
import logging
from enum import IntEnum
from typing import Optional, Iterable, Mapping

import bcrypt
from itsdangerous import TimedJSONWebSignatureSerializer, SignatureExpired, BadSignature
from peewee import Model, CharField, IntegerField
from amcat4.db import db

SECRET_KEY = "NOT VERY SECRET YET!"


class Role(IntEnum):
    METAREADER = 10
    READER = 20
    WRITER = 30
    ADMIN = 40


class User(Model):
    email = CharField(unique=True)
    password = CharField()
    global_role = IntegerField(null=True)

    class Meta:
        database = db

    def create_token(self, expiration: int = None) -> str:
        """
        Create a new token for this user
        """
        s = TimedJSONWebSignatureSerializer(SECRET_KEY, expires_in=expiration)
        return s.dumps({'id': self.id})

    def has_role(self, role: Role) -> bool:
        """
        Check whether this user has at least the requested Role
        """
        return self.global_role and self.global_role >= role

    def indices(self, include_guest: bool = False) -> Mapping['Index', Role]:
        from amcat4.index import Index  # Prevent circular import
        indices = {i.index: Role(i.role) for i in self.indexrole_set.join(Index)}
        if include_guest:
            for i in Index.select().where(Index.guest_role != None):
                if i not in indices:
                    indices[i] = Role(i.guest_role)
        return indices

    @property
    def role(self):
        return self.global_role and Role(self.global_role)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_user(email: str, password: str, global_role: Role = None) -> User:
    """
    Create and return a new User with the given information
    """
    if global_role not in [None, Role.WRITER, Role.ADMIN]:
        raise ValueError("Global roles can only be None, Writer, or Admin")
    return User.create(email=email, password=hash_password(password), global_role=global_role)


def verify_user(email: str, password: str) -> Optional[User]:
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


def verify_token(token: str) -> Optional[User]:
    """
    Check the token and return the authenticated user email
    :param token: The token to verify
    :return: a User object if user could be authenticated, None otherwise
    """
    s = TimedJSONWebSignatureSerializer(SECRET_KEY)
    try:
        result = s.loads(token)
    except (SignatureExpired, BadSignature):
        logging.exception("Token verification failed")
        return None
    logging.warning("TOKEN RESULT: {}" .format(result))
    return User.get(User.id == result['id'])
