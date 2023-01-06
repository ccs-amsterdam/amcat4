from datetime import datetime

import responses
from authlib.jose import jwt
from starlette.testclient import TestClient

from amcat4.config import get_settings
from tests.tools import get_json


@responses.activate
def test_handler_responses(client: TestClient, admin):
    def test(expected=200, **payload):
        header = {'alg': 'RS256'}
        token = jwt.encode(header, payload, PRIVATE_KEY)
        headers = {'Authorization': f"Bearer {token.decode('utf-8')}"}
        return get_json(client, "/users/me", headers=headers, expected=expected)

    get_settings().middlecat_url = "http://localhost:5000"
    get_settings().host = "http://localhost:3000"
    responses.get("http://localhost:5000/api/configuration", json={"public_key": PUBLIC_KEY})
    # You need to login to access /users/me
    assert client.get("/users/me").status_code == 401
    # A valid token needs a valid resource, expiry, and email
    now = int(datetime.now().timestamp())
    test(resource='http://localhost:3000', email=admin, expected=401)
    test(exp=now+1000, email=admin, expected=401)
    assert test(resource='http://localhost:3000', exp=now + 1000, email=admin)['email'] == admin
    # Expired tokens don't work
    test(resource='http://localhost:3000', exp=now - 1000, email=admin, expected=401)
    # Wrong resource
    test(resource='http://wrong.com', exp=now + 1000, email=admin, expected=401)


def test_middlecat_config(client: TestClient):
    result = get_json(client, "/middlecat")
    assert result['middlecat_url'] == get_settings().middlecat_url


PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
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
-----END RSA PRIVATE KEY-----"""

PUBLIC_KEY = """
-----BEGIN RSA PUBLIC KEY-----
MIICCgKCAgEA6rl4vic+CLmfTNEvnl6gliVs+nk/wxkbfnHwhGQz6UYD54RfcOrr
N2kOqnt71RUuLu8fvGS3pDIoV0CEQfmwqmd3dx/QVHXQh7zdOJ1Jv0UKlzGP/2Y4
bLpZrqTZacJa8PMHxyQi0syZvGAN67eUMdAKm5qOntw4crjNXIYXTRYVcD51a9ac
d7hCWmCCJv3BSBQo3btlbylWoOm2GhASwos88tX/xeJ6qfHQ1jNYBfTlc7GKS2ZY
5HdPG49alJKChRHAtGoxDMS8aPergPaeNny/yxJEJbSiwbKcqGqzF7tNkcyM1777
kk5xqcBFWOA/dcYHBgL2NEjEmR8DgSpwpKmaIdntWQqdor+3ld6ruY+yT2r4KvJy
IYQBGEadi5ic4PsJw1cfP9xXn6zKxGdykvF/X/iRlwP6U4e/cFHMU3pbEo12mjyn
ROlHNEgOg9khdTqf7uWFycP6oLZHf9QqNUYOJa29sX1HrB20roi3UjgsAEFoDk0z
03KSHTY64TR16yt0bVPoDHzktO/JIBqSuRkB8AoVxtOpzJgbSxYcbzXPyzeLK0Pr
sMoKjgT48G6UgGUPkNA5YvlE09xLm7K2zyj209lMJAWRs+vmnjmtRRWsHhffomSk
diASy7sRDuQbKCNKoiZyIa4vG9WxH242pZ+/Q8gjI8zskeKkMlJsPYcCAwEAAQ==
-----END RSA PUBLIC KEY-----
"""
