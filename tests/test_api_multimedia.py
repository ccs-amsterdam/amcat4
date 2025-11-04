from fastapi.testclient import TestClient
import pytest
import requests
from amcat4.models import Roles
from amcat4.objectstorage import s3bucket
from amcat4.systemdata.roles import create_project_role
from tests.tools import build_headers, check

if not s3bucket.s3_enabled():
    pytest.skip("S3 not configured, skipping multimedia tests", allow_module_level=True)


def _get_names(client: TestClient, index_with_bucket, user, **kargs):
    res = client.get(f"index/{index_with_bucket}/multimedia/list", params=kargs, headers=build_headers(user))
    res.raise_for_status()
    data = res.json()
    return {obj["key"] for obj in data["items"]}


def test_authorisation(client, index_with_bucket, user, reader):
    check(client.get(f"index/{index_with_bucket}/multimedia/list"), 403)
    check(client.get(f"index/{index_with_bucket}/multimedia/presigned_get", params=dict(key="")), 403)
    check(client.get(f"index/{index_with_bucket}/multimedia/presigned_post/somefield"), 403)

    create_project_role(user, index_with_bucket, Roles.METAREADER)
    create_project_role(reader, index_with_bucket, Roles.READER)
    check(client.get(f"index/{index_with_bucket}/multimedia/list", headers=build_headers(user)), 403)
    check(
        client.get(f"index/{index_with_bucket}/multimedia/presigned_get", params=dict(key=""), headers=build_headers(user)),
        403,
    )
    check(client.get(f"index/{index_with_bucket}/multimedia/presigned_post/somefield", headers=build_headers(reader)), 403)


def test_presigned(client, index_with_bucket, user):
    create_project_role(user, index_with_bucket, Roles.WRITER)
    assert _get_names(client, index_with_bucket, user) == set()

    client.post(f"index/{index_with_bucket}/fields", headers=build_headers(user), json={"image_field": "image"})
    post = client.get(f"index/{index_with_bucket}/multimedia/presigned_post/image_field", headers=build_headers(user)).json()
    assert set(post.keys()) == {"url", "form_data", "key_prefix", "type_prefix"}

    ## TODO: somehow when the upload is forbidden, S3 returns a 307 redirect instead of an error.
    ## Figure out why and how to make it act less stupid.

    ## errors if key doesn't match key prefix
    assert (
        requests.post(
            url=post["url"],
            data={**post["form_data"], "key": "forbidden/file.png", "Content-Type": "image/png"},
            files={"file": ("dummyname", b"bytes")},
            allow_redirects=False,
        ).status_code
        == 307
    )
    ## errors if content type doesn't match type prefix
    assert (
        requests.post(
            url=post["url"],
            data={**post["form_data"], "key": "multimedia/image_field/file.png", "Content-Type": "application/pdf"},
            files={"file": ("dummyname", b"bytes")},
            allow_redirects=False,
        ).status_code
        == 307
    )

    ## works with correct key and content type
    key = post["key_prefix"] + "subfolder/file.png"
    type = post["type_prefix"] + "png"
    assert (
        requests.post(
            url=post["url"],
            data={**post["form_data"], "key": key, "Content-Type": type},
            files={"file": ("dummyname", b"bytes")},
        ).status_code
        == 204
    )

    assert _get_names(client, index_with_bucket, user, recursive=True) == {"image_field/subfolder/file.png"}

    ## this endpoint redirects to a presigned url
    res = client.get(
        f"index/{index_with_bucket}/multimedia/fields/image_field/subfolder/file.png", headers=build_headers(user)
    )
    res.raise_for_status()
    ## CURRENT BUG: S3 returns 403 here instead of the file. Investigate later.
    print(res.content)


def test_list_options(client, index_with_bucket, reader):
    create_project_role(reader, index_with_bucket, Roles.READER)
    bucket = s3bucket.bucket_name(index_with_bucket)
    s3bucket.add_s3_object(bucket, "myfolder/a1", b"a1")
    s3bucket.add_s3_object(bucket, "myfolder/a2", b"a2")
    s3bucket.add_s3_object(bucket, "obj1", b"obj1")
    s3bucket.add_s3_object(bucket, "obj2", b"obj2")
    s3bucket.add_s3_object(bucket, "obj3", b"obj3")
    s3bucket.add_s3_object(bucket, "zzz", b"zzz")

    assert _get_names(client, index_with_bucket, reader) == {"obj1", "obj2", "obj3", "myfolder/", "zzz"}
    assert _get_names(client, index_with_bucket, reader, recursive=True) == {
        "obj1",
        "obj2",
        "obj3",
        "myfolder/a1",
        "myfolder/a2",
        "zzz",
    }
    assert _get_names(client, index_with_bucket, reader, prefix="obj") == {"obj1", "obj2", "obj3"}
    assert _get_names(client, index_with_bucket, reader, prefix="myfolder/") == {"myfolder/a1", "myfolder/a2"}
    assert _get_names(client, index_with_bucket, reader, prefix="myfolder/", presigned_get=True) == {
        "myfolder/a1",
        "myfolder/a2",
    }
    res = client.get(
        f"index/{index_with_bucket}/multimedia/list",
        params=dict(prefix="myfolder/", presigned_get=True),
        headers=build_headers(reader),
    )
    res.raise_for_status()
    assert all("presigned_get" in o for o in res.json()["items"])


def test_list_pagination(client, index_with_bucket, reader):
    create_project_role(reader, index_with_bucket, Roles.READER)
    bucket = s3bucket.bucket_name(index_with_bucket)

    ids = [f"obj_{i:02}" for i in range(110)]
    for id in ids:
        s3bucket.add_s3_object(bucket, id, id.encode("utf-8"))

    # default page size is 50
    res = client.get(f"index/{index_with_bucket}/multimedia/list", headers=build_headers(reader))
    data = res.json()
    assert len(data["items"]) == 50
    assert not data["is_last_page"]

    # Get next page
    token = data["next_page_token"]
    res = client.get(
        f"index/{index_with_bucket}/multimedia/list", headers=build_headers(reader), params=dict(next_page_token=token)
    )
    data = res.json()
    assert len(data["items"]) == 50
    assert not data["is_last_page"]

    # last page
    token = data["next_page_token"]
    res = client.get(
        f"index/{index_with_bucket}/multimedia/list", headers=build_headers(reader), params=dict(next_page_token=token)
    )
    data = res.json()
    assert data["is_last_page"]
