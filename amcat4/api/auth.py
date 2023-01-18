"""Helper methods for authentication."""
import functools
import json
import logging
from datetime import datetime

import requests
from authlib.common.errors import AuthlibBaseError
from authlib.jose import JsonWebSignature
from authlib.jose import jwt
from fastapi import HTTPException
from fastapi.params import Depends
from fastapi.security import OAuth2PasswordBearer
from starlette.status import HTTP_401_UNAUTHORIZED

from amcat4.config import get_settings
from amcat4.index import Role, get_role, get_global_role

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


class InvalidToken(ValueError):
    pass


def create_token(email: str, days_valid: int = 7) -> bytes:
    """
    Create a new (instance) token for this user
    :param email: the email or username to create a token for
    :param days_valid: the number of days from now that the token should be valid
    """
    header: dict = {'alg': 'HS256'}
    now = int(datetime.now().timestamp())
    exp = now + days_valid * 24 * 60 * 60
    payload = {'email': email, 'exp': exp, 'resource': get_settings().host}
    s = JsonWebSignature().serialize_compact(header, json.dumps(payload).encode("utf-8"), get_settings().secret_key)
    return s


@functools.lru_cache()
def get_middlecat_config(middlecat_url) -> dict:
    r = requests.get(f"{middlecat_url}/api/configuration")
    r.raise_for_status()
    return r.json()


def verify_token(token: str) -> dict:
    """
    Verifies the given token and returns the payload

    raises a InvalidToken exception if the token could not be validated
    """
    payload = decode_middlecat_token(token)
    if missing := {'email', 'resource', 'exp'} - set(payload.keys()):
        raise InvalidToken(f"Invalid token, missing keys {missing}")
    now = int(datetime.now().timestamp())
    if payload['exp'] < now:
        raise InvalidToken("Token expired")
    if payload['resource'] != get_settings().host:
        raise InvalidToken(f"Wrong host! {payload['resource']} != {get_settings().host}")
    return payload


def decode_middlecat_token(token: str) -> dict:
    """
    Verifies a midddlecat token
    """
    url = get_settings().middlecat_url
    if not url:
        raise InvalidToken("No middlecat defined, cannot decrypt middlecat token")
    public_key = get_middlecat_config(url)['public_key']
    try:
        return jwt.decode(token, public_key)
    except AuthlibBaseError as e:
        raise InvalidToken(e)


def check_global_role(user: str, required_role: Role, raise_error=True):
    """
    Check if the given user has at least the required role
    :param user: The email address of the authenticated user
    :param required_role: The minimum global role of the user
    :param raise_error: If true, raise an error when not authorized, otherwise return False
                        (will always raise an error if user is not authenticated)
    """
    if not user:
        raise HTTPException(status_code=401, detail="No authenticated user")
    if user == "admin":
        return True
    global_role = get_global_role(user)
    if global_role and global_role >= required_role:
        return True
    if raise_error:
        raise HTTPException(status_code=401, detail=f"User {user} does not have global role {required_role}")
    else:
        return False


def check_role(user: str, required_role: Role, index: str, required_global_role: Role = Role.ADMIN):
    """Check if the given user have at least the given role (in the index, if given), raise Exception otherwise.

    :param user: The email address of the authenticated user
    :param required_role: The minimum role of the user on the given index
    :param index: The index to check the role on
    :param required_global_role: If the user has this global role (default: admin), also allow them access
    """
    # First, check global role (also checks that user exists and deals with 'admin' special user)
    if check_global_role(user, required_global_role, raise_error=False):
        return True
    # Global role check was false, so now check local role
    actual_role = get_role(index, user)
    if actual_role and actual_role >= required_role:
        return True
    else:
        raise HTTPException(status_code=401, detail=f"User {user} does not have role {required_role} on index {index}")


async def authenticated_user(token: str = Depends(oauth2_scheme)):
    """Dependency to verify and return a user based on a token."""
    if not get_settings().require_authorization:
        return "admin"
    else:
        if token is None:
            raise HTTPException(status_code=HTTP_401_UNAUTHORIZED,
                                detail="This instance has no guest access, please provide a valid bearer token")
        try:
            return verify_token(token)['email']
        except Exception:
            logging.exception("Login failed")
            raise HTTPException(status_code=401, detail="Invalid token")


async def authenticated_writer(user: str = Depends(authenticated_user)):
    """Dependency to verify and return a global writer user based on a token."""
    check_global_role(user, Role.WRITER)
    return user


async def authenticated_admin(user: str = Depends(authenticated_user)):
    """Dependency to verify and return a global writer user based on a token."""
    check_global_role(user, Role.ADMIN)
    return user
