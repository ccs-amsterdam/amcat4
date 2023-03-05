"""Helper methods for authentication."""
import functools
import logging
from datetime import datetime

import requests
from authlib.common.errors import AuthlibBaseError
from authlib.jose import jwt
from fastapi import HTTPException
from fastapi.params import Depends
from fastapi.security import OAuth2PasswordBearer
from starlette.status import HTTP_401_UNAUTHORIZED

from amcat4.config import get_settings, AuthOptions
from amcat4.index import Role, get_role, get_global_role

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


class InvalidToken(ValueError):
    pass


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
    try:
        global_role = get_global_role(user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error on retrieving user {user}: {e}")
    if global_role and global_role >= required_role:
        return True
    if raise_error:
        raise HTTPException(status_code=401, detail=f"User {user} does not have global {required_role.name.title()} permissions on this instance")
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
        raise HTTPException(status_code=401, detail=f"User {user} does not have {required_role.name.title()} permissions on index {index}")


async def authenticated_user(token: str = Depends(oauth2_scheme)) -> str:
    """Dependency to verify and return a user based on a token."""
    auth = get_settings().auth
    if token is None:
        if auth == AuthOptions.no_auth:
            return "admin"
        elif auth == AuthOptions.allow_guests:
            return "guest"
        else:
            raise HTTPException(status_code=HTTP_401_UNAUTHORIZED,
                                detail="This instance has no guest access, please provide a valid bearer token")
    try:
        user = verify_token(token)['email']
    except Exception:
        logging.exception("Login failed")
        raise HTTPException(status_code=401, detail="Invalid token")
    if auth == AuthOptions.authorized_users_only:
        if get_global_role(user) is None:
            raise HTTPException(status_code=401,
                                detail=f"The user {user} is not authorized to access this AmCAT instance")
    return user


async def authenticated_writer(user: str = Depends(authenticated_user)):
    """Dependency to verify and return a global writer user based on a token."""
    if get_settings().auth != AuthOptions.no_auth:
        check_global_role(user, Role.WRITER)
    return user


async def authenticated_admin(user: str = Depends(authenticated_user)):
    """Dependency to verify and return a global writer user based on a token."""
    if get_settings().auth != AuthOptions.no_auth:
        check_global_role(user, Role.ADMIN)
    return user
