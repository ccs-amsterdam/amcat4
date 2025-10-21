import re

from tests.tools import build_headers


def check(client, url, status, message, method="post", user=None, **kargs):
    headers = build_headers(user=user) if user else {}
    r = getattr(client, method)(url, headers=headers, **kargs)
    assert r.status_code == status
    if not re.search(message, r.text.lower()):
        raise AssertionError(f"Status {r.status_code} error {repr(r.text)} does not match pattern {repr(message)}")


def test_documents_unauthorized(
    client,
    index,
    writer,
):
    check(client, "/index/", 403, "requires writer permission", json=dict(id=index))
    check(client, f"/index/{index}/", 403, "requires lister permission", method="get")


def test_error_index_create(client, writer, index):
    for name in ("Test", "_test", "test test"):
        check(client, "/index/", 422, "there was an issue with the data you sent", json=dict(id=name), user=writer)
    check(client, "/index/", 409, "already exists", json=dict(id=index), user=writer)
