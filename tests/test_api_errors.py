import re

from amcat4.elastic import es
from tests.tools import amcat_settings, build_headers


def test_documents_unauthorized(client, index, writer, admin):
    def check(url, status, message, method="post", user=None, **kargs):
        headers = build_headers(user=user) if user else {}
        r = getattr(client, method)(url, headers=headers, **kargs)
        assert r.status_code == status
        if not re.search(message, r.text.lower()):
            raise AssertionError(f"Status {r.status_code} error {repr(r.text)} does not match pattern {repr(message)}")

    check("/index/", 401, "global writer permissions")
    for name in ("Test", "_test", "test test"):
        check("/index/", 400, "invalid index name", json=dict(name=name), user=writer)
    check(f"/index/{index}/", 401, f"permissions on index {index}", method='get')

    for hostname in ("doesnotexist.example.com", "https://doesnotexist.example.com:9200"):
        with amcat_settings(elastic_host=hostname):
            es.cache_clear()
            check(f"/index/{index}/", 500, f"cannot connect.*{hostname}", method='get', user=admin)
