"""Helper methods for authentication and authorization."""

import functools
import logging
from datetime import datetime

import requests
from authlib.common.errors import AuthlibBaseError
from authlib.jose import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from starlette.status import HTTP_401_UNAUTHORIZED

from amcat4.config import AuthOptions, get_settings
from amcat4.systemdata.roles import ADMIN_USER, GUEST_USER, raise_if_not_has_role

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
    if missing := {"email", "resource", "exp"} - set(payload.keys()):
        raise InvalidToken(f"Invalid token, missing keys {missing}")
    now = int(datetime.now().timestamp())
    if payload["exp"] < now:
        raise InvalidToken("Token expired")
    if payload["resource"] != get_settings().host:
        raise InvalidToken(f"Wrong host! {payload['resource']} != {get_settings().host}")
    return payload


def decode_middlecat_token(token: str) -> dict:
    """
    Verifies a midddlecat token
    """
    url = get_settings().middlecat_url
    if not url:
        raise InvalidToken("No middlecat defined, cannot decrypt middlecat token")
    public_key = get_middlecat_config(url)["public_key"]
    try:
        return jwt.decode(token, public_key)
    except AuthlibBaseError as e:
        raise InvalidToken(e)


async def authenticated_user(token: str | None = Depends(oauth2_scheme)) -> str:
    """Dependency to verify and return a user based on a token."""
    auth = get_settings().auth
    if token is None:
        if auth == AuthOptions.no_auth:
            return ADMIN_USER
        elif auth == AuthOptions.allow_guests:
            return GUEST_USER
        else:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="This instance has no guest access, please provide a valid bearer token",
            )
    try:
        email = verify_token(token)["email"]
    except Exception:
        logging.exception("Login failed")
        raise HTTPException(status_code=401, detail="Invalid token")

    return email


async def authenticated_writer(user: str = Depends(authenticated_user)):
    """Dependency to verify and return a global writer user based on a token."""
    raise_if_not_has_role(user, "_server", "WRITER")
    return user


async def authenticated_admin(user: str = Depends(authenticated_user)):
    """Dependency to verify and return a global writer user based on a token."""
    raise_if_not_has_role(user, "_server", "ADMIN")
    return user
