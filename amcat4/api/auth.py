"""Helper methods for authentication and authorization."""

import logging
from datetime import datetime

import httpx
from async_lru import alru_cache
from authlib.common.errors import AuthlibBaseError
from authlib.jose import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from amcat4.config import AuthOptions, get_settings
from amcat4.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


class InvalidToken(ValueError):
    pass


@alru_cache(maxsize=1)
async def get_middlecat_config(middlecat_url) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{middlecat_url}/api/configuration")
        r.raise_for_status()
        return r.json()


async def verify_token(token: str) -> dict:
    """
    Verifies the given token and returns the payload

    raises a InvalidToken exception if the token could not be validated
    """
    payload = await decode_middlecat_token(token)
    if missing := {"email", "resource", "exp"} - set(payload.keys()):
        raise InvalidToken(f"Invalid token, missing keys {missing}")
    now = int(datetime.now().timestamp())
    if payload["exp"] < now:
        raise InvalidToken("Token expired")
    if payload["resource"] != get_settings().host:
        raise InvalidToken(f"Wrong host! {payload['resource']} != {get_settings().host}")
    return payload


async def decode_middlecat_token(token: str) -> dict:
    """
    Verifies a midddlecat token
    """
    url = get_settings().middlecat_url
    if not url:
        raise InvalidToken("No middlecat defined, cannot decrypt middlecat token")
    public_key = (await get_middlecat_config(url))["public_key"]
    try:
        return jwt.decode(token, public_key)
    except AuthlibBaseError as e:
        raise InvalidToken(e)


async def authenticated_user(token: str | None = Depends(oauth2_scheme)) -> User:
    """Dependency to verify and return a user based on a token."""
    settings = get_settings()
    if token is None:
        if settings.auth == AuthOptions.no_auth:
            return User(email=None, superadmin=True)
        elif settings.auth == AuthOptions.allow_guests:
            return User(email=None)
        else:  # settings.auth == AuthOptions.allow_authenticated_guests:
            raise HTTPException(
                status_code=401,
                detail="This instance requires guests to be authenticated. Please provide a valid bearer token",
            )
    try:
        email = (await verify_token(token))["email"]
    except Exception:
        logging.exception("Login failed")
        raise HTTPException(status_code=401, detail="Invalid token")

    if settings.auth == AuthOptions.no_auth or email == settings.admin_email:
        return User(email=email, superadmin=True)
    else:
        return User(email=email)
