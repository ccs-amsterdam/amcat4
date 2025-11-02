from io import BytesIO
import os
import pytest
import requests
from amcat4.multimedia import objectstorage

if not objectstorage.s3_enabled():
    pytest.skip("S3 not configured, skipping multimedia tests", allow_module_level=True)

## TODO: make a conftest fixtures for a bucket that is cleaned up after each test.
## Also always add a required argument for a bucket prefix, that can be "projects", "systemdata" and "test/projects", etc


def test_upload_get_s3(index):
    bucket = objectstorage.get_bucket(index)
    assert objectstorage.list_s3_objects(bucket) == {"items": [], "next_page_token": None, "is_last_page": True}
    objectstorage.add_s3_object(bucket, "test", b"bytes")
    assert {o["key"] for o in objectstorage.list_s3_objects(bucket)["items"]} == {"test"}


def test_presigned_form(index):
    bucket = objectstorage.get_bucket(index)
    assert list(objectstorage.list_s3_objects(bucket)) == {"items": [], "next_page_token": None, "is_last_page": True}
    bytes = os.urandom(32)
    key = "image.png"

    url, form_data = objectstorage.presigned_post(bucket, "")
    res = requests.post(
        url=url,
        data={"key": key, **form_data},
        files={"file": BytesIO(bytes)},
    )
    res.raise_for_status()
    assert {o["key"] for o in objectstorage.list_s3_objects(bucket)["items"]} == {"image.png"}

    url = objectstorage.presigned_get(bucket, key)
    res = requests.get(url)
    res.raise_for_status()
    assert res.content == bytes
