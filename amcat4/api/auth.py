"""Helper methods for authentication and authorization."""

import logging
from datetime import datetime

import httpx
from async_lru import alru_cache
from authlib.common.errors import AuthlibBaseError
from authlib.jose import JsonWebToken, jwt
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader, OpenIdConnect
from fastapi.security.oauth2 import OAuth2AuthorizationCodeBearer

from amcat4.config import AuthOptions, get_settings
from amcat4.models import User
from amcat4.systemdata.apikeys import get_api_key

middlecat_url = get_settings().middlecat_url.rstrip("/")
middlecat_scheme = OAuth2AuthorizationCodeBearer(
    tokenUrl=f"{middlecat_url}/api/token",
    authorizationUrl=f"{middlecat_url}/authorize",
    refreshUrl="/auth/token",
    auto_error=False,
    scheme_name="OAuth2 Scheme",
)

oidc_scheme = (
    OpenIdConnect(
        openIdConnectUrl=get_settings().oidc_url or "",
        auto_error=False,
        scheme_name="OIDC Scheme",
    )
    if get_settings().oidc_url is not None
    else None
)

api_key_scheme = APIKeyHeader(name="X-API-Key", scheme_name="API Key Header", auto_error=False)


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


async def validate_oidc_token(token: str) -> dict:
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


async def authenticated_user(
    api_key: str | None = Security(api_key_scheme),
    middlecat: str | None = Security(middlecat_scheme),
    oidc: str | None = Security(oidc_scheme),
) -> User:
    """
    Authenticates the user based on the provided middlecat token, oidc token or api key.
    """
    settings = get_settings()
    auth_disabled = settings.auth == AuthOptions.no_auth

    if middlecat is not None:
        try:
            t = await verify_token(middlecat)
            return User(
                email=t["email"],
                auth_disabled=auth_disabled,
                superadmin=t["email"] == settings.admin_email,
                auth_method="middlecat",
            )
        except Exception as e:
            logging.exception("Middlecat Login failed: " + str(e))
            raise HTTPException(status_code=401, detail="Invalid MiddleCat token: " + str(e)) from e

    elif oidc is not None:
        try:
            t = await validate_oidc_token(oidc)
            return User(
                email=t["email"],
                auth_disabled=auth_disabled,
                superadmin=t["email"] == settings.admin_email,
                auth_method="oidc",
            )
        except Exception as e:
            logging.exception("OIDC login failed: " + str(e))
            raise HTTPException(status_code=401, detail="Invalid OIDC token: " + str(e)) from e

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
