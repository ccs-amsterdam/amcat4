import re

from amcat4.elastic import es
from tests.tools import amcat_settings, build_headers


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
    check(client, "/index/", 401, "global writer permissions")
    check(client, f"/index/{index}/", 401, f"permissions on index {index}", method="get")


def test_error_elastic(client, index, admin):
    for hostname in ("doesnotexist.example.com", "https://doesnotexist.example.com:9200"):
        with amcat_settings(elastic_host=hostname, elastic_verify_ssl=True):
            es.cache_clear()
            check(client, f"/index/{index}/", 500, f"cannot connect.*{hostname}", method="get", user=admin)


def test_error_index_create(client, writer, index):
    for name in ("Test", "_test", "test test"):
        check(client, "/index/", 400, "invalid index name", json=dict(id=name), user=writer)
    check(client, "/index/", 400, "already exists", json=dict(id=index), user=writer)
