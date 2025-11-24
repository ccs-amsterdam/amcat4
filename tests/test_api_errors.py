import re

import pytest

from tests.tools import build_headers


@pytest.mark.anyio
async def check(client, url, status, message, method="post", user=None, **kargs):
    headers = build_headers(user=user) if user else {}
    r = await getattr(client, method)(url, headers=headers, **kargs)
    print(r.content)
    print(r.headers)
    assert r.status_code == status
    if not re.search(message, r.text.lower()):
        raise AssertionError(f"Status {r.status_code} error {repr(r.text)} does not match pattern {repr(message)}")


@pytest.mark.anyio
async def test_documents_unauthorized(
    client,
    index,
):
    await check(client, "/index", 403, "requires writer permission", json=dict(id=index))
    await check(client, f"/index/{index}", 403, "does not have", method="get")


@pytest.mark.anyio
async def test_error_index_create(client, writer, index):
    for name in ("Test", "_test", "test test"):
        await check(client, "/index", 422, "there was an issue with the data you sent", json=dict(id=name), user=writer)
    await check(client, "/index", 409, "already exists", json=dict(id=index), user=writer)
