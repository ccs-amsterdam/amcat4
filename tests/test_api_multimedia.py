from fastapi.testclient import TestClient
import pytest
import requests
from amcat4 import multimedia
from amcat4.index import set_role, Role
from tests.tools import post_json, build_headers, get_json, check


def _get_names(client: TestClient, index, user, **kargs):
    res = client.get(f"index/{index}/multimedia/list", params=kargs, headers=build_headers(user))
    res.raise_for_status()
    return {obj["key"] for obj in res.json()}


def test_authorisation(minio, client, index, user, reader):
    check(client.get(f"index/{index}/multimedia/list"), 401)
    check(client.get(f"index/{index}/multimedia/presigned_get", params=dict(key="")), 401)
    check(client.get(f"index/{index}/multimedia/presigned_post"), 401)

    set_role(index, user, Role.METAREADER)
    set_role(index, reader, Role.READER)
    check(client.get(f"index/{index}/multimedia/list", headers=build_headers(user)), 401)
    check(client.get(f"index/{index}/multimedia/presigned_get", params=dict(key=""), headers=build_headers(user)), 401)
    check(client.get(f"index/{index}/multimedia/presigned_post", headers=build_headers(reader)), 401)


def test_post_get_list(minio, client, index, user):
    pytest.skip("mock minio does not allow presigned post, skipping for now")
    set_role(index, user, Role.WRITER)
    assert _get_names(client, index, user) == set()
    post = client.get(f"index/{index}/multimedia/presigned_post", headers=build_headers(user)).json()
    assert set(post.keys()) == {"url", "form_data"}
    multimedia.add_multimedia_object(index, "test", b"bytes")
    assert _get_names(client, index, user) == {"test"}
    res = client.get(f"index/{index}/multimedia/presigned_get", headers=build_headers(user), params=dict(key="test"))
    res.raise_for_status()
    assert requests.get(res.json()["url"]).content == b"bytes"


def test_list_options(minio, client, index, reader):
    set_role(index, reader, Role.READER)
    multimedia.add_multimedia_object(index, "myfolder/a1", b"a1")
    multimedia.add_multimedia_object(index, "myfolder/a2", b"a2")
    multimedia.add_multimedia_object(index, "obj1", b"obj1")
    multimedia.add_multimedia_object(index, "obj2", b"obj2")
    multimedia.add_multimedia_object(index, "obj3", b"obj3")
    multimedia.add_multimedia_object(index, "zzz", b"zzz")

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


def test_list_pagination(minio, client, index, reader):
    set_role(index, reader, Role.READER)
    ids = [f"obj_{i:02}" for i in range(15)]
    for id in ids:
        multimedia.add_multimedia_object(index, id, id.encode("utf-8"))

    # default page size is 10
    names = _get_names(client, index, reader)
    assert names == set(ids[:10])
    more_names = _get_names(client, index, reader, start_after=ids[9])
    assert more_names == set(ids[10:])

    names = _get_names(client, index, reader, n=5)
    assert names == set(ids[:5])
