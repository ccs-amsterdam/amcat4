from fastapi.testclient import TestClient
import pytest
import requests
from amcat4.models import Roles
from amcat4.multimedia import objectstorage
from amcat4.systemdata.roles import create_project_role
from tests.tools import post_json, build_headers, get_json, check

if not objectstorage.s3_enabled():
    pytest.skip("S3 not configured, skipping multimedia tests", allow_module_level=True)


def _get_names(client: TestClient, index, user, **kargs):
    res = client.get(f"index/{index}/multimedia/list", params=kargs, headers=build_headers(user))
    res.raise_for_status()
    return {obj["key"] for obj in res.json()}


def test_authorisation(client, index, user, reader):
    check(client.get(f"index/{index}/multimedia/list"), 401)
    check(client.get(f"index/{index}/multimedia/presigned_get", params=dict(key="")), 401)
    check(client.get(f"index/{index}/multimedia/presigned_post"), 401)

    create_project_role(user, index, Roles.METAREADER)
    create_project_role(reader, index, Roles.READER)
    check(client.get(f"index/{index}/multimedia/list", headers=build_headers(user)), 401)
    check(client.get(f"index/{index}/multimedia/presigned_get", params=dict(key=""), headers=build_headers(user)), 401)
    check(client.get(f"index/{index}/multimedia/presigned_post", headers=build_headers(reader)), 401)


def test_post_get_list(client, index, user):
    create_project_role(user, index, Roles.WRITER)
    assert _get_names(client, index, user) == set()
    post = client.get(f"index/{index}/multimedia/presigned_post", headers=build_headers(user)).json()
    assert set(post.keys()) == {"url", "form_data"}
    objectstorage.add_s3_object(index, "test", b"bytes")
    assert _get_names(client, index, user) == {"test"}
    res = client.get(f"index/{index}/multimedia/presigned_get", headers=build_headers(user), params=dict(key="test"))
    res.raise_for_status()
    assert requests.get(res.json()["url"]).content == b"bytes"


def test_list_options(client, index, reader):
    create_project_role(reader, index, Roles.READER)
    objectstorage.add_s3_object(index, "myfolder/a1", b"a1")
    objectstorage.add_s3_object(index, "myfolder/a2", b"a2")
    objectstorage.add_s3_object(index, "obj1", b"obj1")
    objectstorage.add_s3_object(index, "obj2", b"obj2")
    objectstorage.add_s3_object(index, "obj3", b"obj3")
    objectstorage.add_s3_object(index, "zzz", b"zzz")

    assert _get_names(client, index, reader) == {"obj1", "obj2", "obj3", "myfolder/", "zzz"}
    assert _get_names(client, index, reader, recursive=True) == {"obj1", "obj2", "obj3", "myfolder/a1", "myfolder/a2", "zzz"}
    assert _get_names(client, index, reader, prefix="obj") == {"obj1", "obj2", "obj3"}
    assert _get_names(client, index, reader, prefix="myfolder/") == {"myfolder/a1", "myfolder/a2"}
    assert _get_names(client, index, reader, prefix="myfolder/", presigned_get=True) == {"myfolder/a1", "myfolder/a2"}
    res = client.get(
        f"index/{index}/multimedia/list", params=dict(prefix="myfolder/", presigned_get=True), headers=build_headers(reader)
    )
    res.raise_for_status()
    assert all("presigned_get" in o for o in res.json())


def test_list_pagination(client, index, reader):
    create_project_role(reader, index, Roles.READER)
    ids = [f"obj_{i:02}" for i in range(15)]
    for id in ids:
        objectstorage.add_s3_object(index, id, id.encode("utf-8"))

    # default page size is 10
    names = _get_names(client, index, reader)
    assert names == set(ids[:10])
    more_names = _get_names(client, index, reader, start_after=ids[9])
    assert more_names == set(ids[10:])

    names = _get_names(client, index, reader, n=5)
    assert names == set(ids[:5])
