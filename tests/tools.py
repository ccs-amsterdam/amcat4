import json
from base64 import b64encode
from datetime import datetime, date
from typing import Set, Iterable


def build_headers(user=None, headers=None, password=None):
    if not headers:
        headers = {}
    if user and password:
        credentials = b64encode(f"{user}:{password}".encode('ascii')).decode('ascii')
        headers["Authorization"] = f"Basic {credentials}"
    elif user:
        headers['Authorization'] = f"Bearer {user.create_token().decode('utf-8')}"
    return headers


def get_json(client, url, expected=200, headers=None, user=None, **kargs):
    """Get the given URL. If expected is 2xx, return the result as parsed json"""
    response = client.get(url, headers=build_headers(user, headers), **kargs)
    assert response == expected, f"GET {url} returned {response.status_code}, expected {expected}"
    if expected // 100 == 2:
        return json.loads(response.get_data(as_text=True))


def post_json(client, url, expected=201, headers=None, user=None, **kargs):
    response = client.post(url, headers=build_headers(user, headers), **kargs)
    assert response == expected, f"POST {url} returned {response.status_code}, expected {expected}"
    return json.loads(response.get_data(as_text=True))


class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return json.JSONEncoder.default(self, o)


def dictset(dicts: Iterable[dict]) -> Set[str]:
    """Helper method to convert an iterable of dicts into a comparable set of sorted json strings"""
    return {json.dumps(dict(sorted(d.items())), cls=DateTimeEncoder) for d in dicts}
