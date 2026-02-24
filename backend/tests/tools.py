import json
import base64
from base64 import b64encode
from contextlib import contextmanager
from datetime import date, datetime
from typing import Iterable, Optional, Set

import itsdangerous
from authlib.jose import jwt
from httpx import AsyncClient

from amcat4.config import AuthOptions, get_settings
from tests.middlecat_keypair import PRIVATE_KEY


def create_token(**payload) -> str:
    header = {"alg": "RS256"}
    token = jwt.encode(header, payload, PRIVATE_KEY)
    return token.decode("utf-8")

def create_session_cookie(data: dict):
    """Immitate how Starlette signs the session cookie."""
    secret_key = get_settings().cookie_secret
    signer = itsdangerous.TimestampSigner(str(secret_key))
    json_data = json.dumps(data).encode("utf-8")
    base64_data = b64encode(json_data)
    return signer.sign(base64_data).decode("utf-8")

def auth_cookie(user=None, cookies=None):
    if not user:
        return cookies

    token = create_token(
        clientId=get_settings().host,
        resource=get_settings().host + "/api",
        email=user,
        exp=int(datetime.now().timestamp()) + 1000,
    )
    session_data = {"access_token": token}
    signed_cookie = create_session_cookie( data=session_data )

    if not cookies:
        cookies = {}
    cookies["amcat_session"] = signed_cookie
    return cookies


async def get_json(client: AsyncClient, url: str, expected=200, cookies=None, headers=None, user=None, **kargs) -> dict:
    """Get the given URL. If expected is 2xx, return the result as parsed json"""
    response = await client.get(url, cookies=auth_cookie(user, cookies), headers=headers, **kargs)
    content = response.json() if response.content else None
    assert response.status_code == expected, f"GET {url} returned {response.status_code}, expected {expected}, {content}"
    return {} if content is None else content


async def post_json(client: AsyncClient, url, expected=201, cookies=None, headers=None, user=None, **kargs):
    response = await client.post(url, cookies=auth_cookie(user, cookies), headers=headers, **kargs)
    assert response.status_code == expected, (
        f"POST {url} returned {response.status_code}, expected {expected}\n{response.json() if response.content else ''}"
    )
    if expected == 204:
        return {}
    else:
        return response.json()


async def put_json(client: AsyncClient, url, expected=200, cookies=None, headers=None, user=None, **kargs):
    response = await client.put(url, cookies=auth_cookie(user, cookies), headers=headers, **kargs)
    assert response.status_code == expected, (
        f"PUT {url} returned {response.status_code}, expected {expected}\n{response.json()}"
    )
    if expected == 204:
        return {}
    else:
        return response.json()


async def adelete(client: AsyncClient, url, expected=204, cookies=None, headers=None, user=None, **kargs):
    response = await client.delete(url, cookies=auth_cookie(user, cookies), headers=headers, **kargs)
    assert response.status_code == expected, (
        f"DELETE {url} returned {response.status_code}, expected {expected}\n{response.json()}"
    )
    if expected == 204:
        return {}
    else:
        return response.json()


class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return json.JSONEncoder.default(self, o)


def dictset(dicts: Iterable[dict]) -> Set[str]:
    """Helper method to convert an iterable of dicts into a comparable set of sorted json strings"""
    return {json.dumps(dict(sorted(d.items())), cls=DateTimeEncoder) for d in dicts}


async def check(response, expected: int, msg: Optional[str] = None):
    try:
        content = response.json()
    except Exception:
        content = response.content
    assert response.status_code == expected, (
        f"{msg or ''}{': ' if msg else ''}Unexpected status: received {response.status_code} != expected {expected};"
        f" reply: {content}"
    )


@contextmanager
def set_auth(level: AuthOptions = AuthOptions.allow_authenticated_guests):
    """Context manager to set auth option"""
    old_auth = get_settings().auth
    get_settings().auth = level
    yield level
    get_settings().auth = old_auth


@contextmanager
def amcat_settings(**kargs):
    settings = get_settings()
    old_settings = settings.model_dump()
    try:
        for k, v in kargs.items():
            setattr(settings, k, v)
        yield settings
    finally:
        for k, v in old_settings.items():
            setattr(settings, k, v)
