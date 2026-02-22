"""Helper methods for authentication and authorization."""

import logging
from datetime import datetime

import httpx
from async_lru import alru_cache
from authlib.common.errors import AuthlibBaseError
from authlib.jose import JsonWebToken, jwt
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyCookie, APIKeyHeader, OpenIdConnect
from fastapi.security.oauth2 import OAuth2AuthorizationCodeBearer

from amcat4.config import AuthOptions, get_settings
from amcat4.models import User
from amcat4.systemdata.apikeys import get_api_key

api_key_scheme = APIKeyHeader(name="X-API-Key", scheme_name="API Key Header", auto_error=False)

session_cookie = APIKeyCookie(name="amcat_session", auto_error=False)


async def session_cookie_scheme(request: Request, _=Depends(session_cookie)):
    access_token = request.session.get("access_token")
    return access_token


class InvalidToken(ValueError):
    pass


@alru_cache(maxsize=1)
async def get_middlecat_config(middlecat_url) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{middlecat_url}/api/configuration")
        r.raise_for_status()
        return r.json()


@alru_cache(maxsize=1)
async def get_oidc_jwks():
    oidc_url = get_settings().oidc_url
    if oidc_url is None:
        raise InvalidToken("No OIDC configured")

    async with httpx.AsyncClient() as client:
        url = oidc_url + "/.well-known/openid-configuration"
        r = await client.get(url)
        r.raise_for_status()
        return r.json().get("jwks_uri")


async def verify_middlecat_token(token: str) -> dict:
    url = get_settings().middlecat_url
    if not url:
        raise InvalidToken("No middlecat defined, cannot decrypt middlecat token")
    public_key = (await get_middlecat_config(url))["public_key"]
    payload = jwt.decode(token, public_key)

    if missing := {"email", "resource", "exp"} - set(payload.keys()):
        raise InvalidToken(f"Invalid token, missing keys {missing}")
    now = int(datetime.now().timestamp())
    if payload["exp"] < now:
        raise InvalidToken("Token expired")

    client = get_settings().host
    if payload["clientId"] != client:
        raise InvalidToken(f"Invalid client! {payload['clientId']} != {client}")

    resource = client + "/api"
    if payload["resource"] != resource:
        raise InvalidToken(f"Wrong host! {payload['resource']} != {resource}")
    return payload


async def verify_oidc_token(token: str) -> dict:
    jwks = await get_oidc_jwks()
    rsa_jwt = JsonWebToken(algorithms=["RS256"])
    options: dict = {
        "iss": {"essential": True, "value": get_settings().oidc_url},
        "aud": {"essential": True, "value": get_settings().host},
        "exp": {"essential": True},
    }
    return rsa_jwt.decode(token, key=jwks, claims_options=options)


async def verify_token(token: str) -> dict:
    """
    Verifies the given token and returns the payload

    raises a InvalidToken exception if the token could not be validated
    """
    if get_settings().oidc_url:
        return await verify_oidc_token(token)
    else:
        return await verify_middlecat_token(token)


async def authenticated_user(
    api_key: str | None = Security(api_key_scheme),
    access_token: str | None = Security(session_cookie_scheme),
) -> User:
    """
    Authenticates the user based on the provided middlecat token, oidc token or api key.
    """
    settings = get_settings()
    auth_disabled = settings.auth == AuthOptions.no_auth

    if access_token is not None:
        try:
            t = await verify_token(access_token)
            return User(
                email=t["email"],
                auth_disabled=auth_disabled,
                superadmin=t["email"] == settings.admin_email,
                auth_method="middlecat",
            )
        except Exception as e:
            logging.exception("Login failed: " + str(e))
            raise HTTPException(status_code=401, detail="Invalid token: " + str(e)) from e

    elif api_key is not None:
        try:
            a = await get_api_key(api_key)
            return User(
                email=a.email,
                auth_disabled=auth_disabled,
                superadmin=a.email == settings.admin_email,
                api_key_name=a.name,
                api_key_restrictions=a.restrictions,
                auth_method="api_key",
            )
        except KeyError as e:
            logging.exception("API key login failed: " + str(e))
            raise HTTPException(status_code=401, detail="Invalid API key: " + str(e)) from e

    else:
        if settings.auth == AuthOptions.allow_authenticated_guests:
            raise HTTPException(
                status_code=401,
                detail="This instance requires guests to be authenticated. Please provide a valid bearer token",
            )
        return User(
            email=None,
            auth_disabled=auth_disabled,
            auth_method="none",
        )
