"""
Provide authentication for AmCAT4 api

Currently provides token based authentication using an elasticsearch backend,
assuming a 'amcat4system' index
"""
import logging
from secrets import token_hex

import bcrypt
from itsdangerous import TimedJSONWebSignatureSerializer, Serializer, SignatureExpired, BadSignature
from peewee import Model, CharField, BooleanField
from amcat4.db import db

SECRET_KEY = "NOT VERY SECRET YET!"

ROLE_CREATOR = "CREATOR"
ROLE_ADMIN = "ADMIN"


class User(Model):
    email = CharField(unique=True)
    password = CharField()
    is_admin = BooleanField(default=False)
    is_creator = BooleanField(default=False)

    class Meta:
        database = db

    def create_token(self, expiration: int = None) -> str:
        """
        Create a new token for this user
        """
        s = TimedJSONWebSignatureSerializer(SECRET_KEY, expires_in=expiration)
        return s.dumps({'id': self.id})

    def has_role(self, role):
        if self.is_admin:
            return True
        if role == ROLE_CREATOR and self.is_creator:
            return True


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
    s = TimedJSONWebSignatureSerializer(SECRET_KEY)
    try:
        result = s.loads(token)
    except (SignatureExpired, BadSignature):
        logging.exception("Token verification failed")
        return None
    logging.warning("TOKEN RESULT: {}" .format(result))
    return User.get(User.id == result['id'])
