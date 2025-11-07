import time

import pytest
import requests
from fastapi.testclient import TestClient

from amcat4.elastic.util import index_scan
from amcat4.models import Roles
from amcat4.objectstorage import s3bucket
from amcat4.projects.documents import create_or_update_documents
from amcat4.systemdata.roles import create_project_role
from tests.tools import build_headers, check

if not s3bucket.s3_enabled():
    pytest.skip("S3 not configured, skipping multimedia tests", allow_module_level=True)


def _get_names(client: TestClient, index, user, **kargs):
    res = client.get(f"index/{index}/multimedia", params=kargs, headers=build_headers(user))
    res.raise_for_status()
    data = res.json()
    return {obj["key"] for obj in data["items"]}


def test_authorisation(client, index, user, reader):
    create_or_update_documents(index, documents=[{"_id": "doc1", "image_field": "image.png"}], fields={"image_field": "image"})

    check(client.get(f"index/{index}/multimedia"), 403)
    check(client.get(f"index/{index}/multimedia/doc1/image_field/etag"), 403)
    check(client.get(f"index/{index}/multimedia/upload/doc1/image"), 403)

    create_project_role(user, index, Roles.METAREADER)
    create_project_role(reader, index, Roles.READER)
    check(client.get(f"index/{index}/multimedia", headers=build_headers(user)), 403)
    check(
        client.get(f"index/{index}/multimedia/doc1/image_field/etag", params=dict(key=""), headers=build_headers(user)),
        403,
    )
    check(client.get(f"index/{index}/multimedia/upload/doc1/image", headers=build_headers(reader)), 403)


def test_presigned(client, index, user):
    create_or_update_documents(index, documents=[{"_id": "doc1", "image_field": "image.png"}], fields={"image_field": "image"})
    create_project_role(user, index, Roles.WRITER)

    assert _get_names(client, index, user) == set()

    post = client.get(f"index/{index}/multimedia/upload/doc1/image_field", headers=build_headers(user)).json()
    assert set(post.keys()) == {"url", "form_data", "type_prefix"}

    ## TODO: somehow when the upload is forbidden, S3 returns a 307 redirect instead of an error.
    ## Figure out why and how to make it act less stupid.
    file = {"file": ("dummyname", b"my beautiful image bytes")}

    ## errors if key doesn't match key prefix
    assert (
        requests.post(
            url=post["url"],
            data={**post["form_data"], "key": "forbidden/file.png", "Content-Type": "image/png"},
            files=file,
            allow_redirects=False,
        ).status_code
        == 307
    )
    ## errors if content type doesn't match type prefix
    assert (
        requests.post(
            url=post["url"],
            data={**post["form_data"], "Content-Type": "application/pdf"},
            files=file,
            allow_redirects=False,
        ).status_code
        == 307
    )

    ## works with correct (unchanged) key and content type
    type = post["type_prefix"] + "png"
    res = requests.post(url=post["url"], data={**post["form_data"], "Content-Type": type}, files=file, allow_redirects=False)

    ## When successfull, S3 responds with a 303 redirect to the multimedia/{doc}/{field}/refresh endpoint,
    ## which we need to do manually (ughh) because this request goes to the testing client
    assert res.status_code == 303
    redirect = res.headers["Location"]
    client.get(redirect).raise_for_status()

    assert _get_names(client, index, user) == {"amcat4_unittest_index/doc1/image_field"}

    ## The elastic document should not be updated yet
    res = client.get(f"index/{index}/documents/doc1", headers=build_headers(user))
    assert res.json()["image_field"]["etag"] == "PENDING"

    ## After refreshing, the document should be updated
    client.get(f"index/{index}/multimedia/refresh", headers=build_headers(user)).raise_for_status()
    res = client.get(f"index/{index}/documents/doc1", headers=build_headers(user))
    etag = res.json()["image_field"]["etag"]
    assert etag != "PENDING"

    ## Now we should be able to get the file via the gatekeeper endpoint.
    ## This redirects to a presigned S3 GET url.
    ## We need to manually handle the redirect because of the testing client
    res = client.get(f"index/{index}/multimedia/doc1/image_field/{etag}", headers=build_headers(user), follow_redirects=False)
    assert res.status_code == 307
    presigned_get = res.headers["location"]
    res = requests.get(presigned_get)
    assert res.content == b"my beautiful image bytes"


def test_list_pagination(client, index, reader, user):
    create_project_role(user, index, Roles.WRITER)

    documents = [{"_id": f"doc_{i}", "image_field": "image.png"} for i in range(15)]
    create_or_update_documents(index, documents=documents, fields={"image_field": "image"})
    for doc in documents:
        res = client.get(f"index/{index}/multimedia/upload/{doc['_id']}/image_field", headers=build_headers(user))
        res.raise_for_status()
        post = res.json()
        file = {"file": ("dummyname", b"my beautiful image bytes")}
        requests.post(url=post["url"], data={**post["form_data"], "Content-Type": "image/png"}, files=file)

    create_project_role(reader, index, Roles.READER)

    ## TODO:
    # SeaweedFS kind of sucks. It doesn't delete directories, and if a directory already exists,
    # somehow it 'sometimes' doesn't show up in the listing.
    # might have something to do with allowemptyfolder (see docker compose)

    res = client.get(f"index/{index}/multimedia", params=dict(n=4), headers=build_headers(reader))
    data = res.json()
    assert len(data["items"]) == 4
    assert not data["is_last_page"]

    # Get next page
    token = data["next_page_token"]
    res = client.get(f"index/{index}/multimedia", headers=build_headers(reader), params=dict(next_page_token=token))
    data = res.json()
    assert len(data["items"]) == 4
    assert not data["is_last_page"]

    # last page
    token = data["next_page_token"]
    res = client.get(f"index/{index}/multimedia", headers=build_headers(reader), params=dict(next_page_token=token))
    data = res.json()
    assert data["is_last_page"]
