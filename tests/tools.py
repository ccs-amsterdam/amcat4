import json
from contextlib import contextmanager
from datetime import datetime, date
from typing import Set, Iterable, Optional

import requests
from authlib.jose import jwt
from fastapi.testclient import TestClient

from amcat4.config import AuthOptions, get_settings
from amcat4.index import refresh_index
from tests.middlecat_keypair import PRIVATE_KEY


def create_token(**payload) -> bytes:
    header = {'alg': 'RS256'}
    token = jwt.encode(header, payload, PRIVATE_KEY)
    return token.decode('utf-8')


def build_headers(user=None, headers=None):
    if not headers:
        headers = {}
    if user:
        token = create_token(resource=get_settings().host, email=user, exp=int(datetime.now().timestamp()) + 1000)
        headers['Authorization'] = f"Bearer {token}"
    return headers


def get_json(client: TestClient, url, expected=200, headers=None, user=None, **kargs):
    """Get the given URL. If expected is 2xx, return the result as parsed json"""
    response = client.get(url, headers=build_headers(user, headers), **kargs)
    content = response.json() if response.content else None
    assert response.status_code == expected, \
        f"GET {url} returned {response.status_code}, expected {expected}, {content}"
    if expected // 100 == 2:
        return content


def post_json(client: TestClient, url, expected=201, headers=None, user=None, **kargs):
    response = client.post(url, headers=build_headers(user, headers), **kargs)
    assert response.status_code == expected, f"POST {url} returned {response.status_code}, expected {expected}\n" \
                                             f"{response.json()}"
    if expected != 204:
        return response.json()


class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return json.JSONEncoder.default(self, o)


def dictset(dicts: Iterable[dict]) -> Set[str]:
    """Helper method to convert an iterable of dicts into a comparable set of sorted json strings"""
    return {json.dumps(dict(sorted(d.items())), cls=DateTimeEncoder) for d in dicts}


def check(response: requests.Response, expected: int, msg: Optional[str] = None):
    assert response.status_code == expected, \
        f"{msg or ''}{': ' if msg else ''}Unexpected status: received {response.status_code} != expected {expected};"\
        f" reply: {response.json()}"


@contextmanager
def set_auth(level: AuthOptions = AuthOptions.authorized_users_only):
    """Context manager to set auth option"""
    old_auth = get_settings().auth
    get_settings().auth = level
    yield level
    get_settings().auth = old_auth


@contextmanager
def amcat_settings(**kargs):
    settings = get_settings()
    old_settings = settings.dict()
    try:
        for k, v in kargs.items():
            setattr(settings, k, v)
        yield settings
    finally:
        for k, v in old_settings.items():
            setattr(settings, k, v)


def refresh():
    refresh_index(get_settings().system_index)
