from io import BytesIO
import os
import pytest
import requests
from amcat4.objectstorage.s3bucket import (
    add_s3_object,
    get_index_bucket,
    delete_index_bucket,
    list_s3_objects,
    presigned_get,
    presigned_post,
    s3_enabled,
)

if not s3_enabled():
    pytest.skip("S3 not configured, skipping multimedia tests", allow_module_level=True)


def test_upload_get_s3(index_with_bucket):
    bucket = get_index_bucket(index_with_bucket)
    assert list_s3_objects(bucket) == {"items": [], "next_page_token": None, "is_last_page": True}
    add_s3_object(bucket, "test", b"bytes")
    assert {o["key"] for o in list_s3_objects(bucket)["items"]} == {"test"}


def test_presigned_form(index_with_bucket):
    bucket = get_index_bucket(index_with_bucket)

    assert list_s3_objects(bucket) == {"items": [], "next_page_token": None, "is_last_page": True}
    bytes = os.urandom(32)
    key = "image.png"

    url, form_data = presigned_post(bucket, "")
    print(url)
    res = requests.post(
        url=url,
        data={"Content-Type": "image/png", **form_data},
        files={"file": (key, BytesIO(bytes))},
        # allow_redirects=False,
    )
    res.raise_for_status()
    assert {o["key"] for o in list_s3_objects(bucket)["items"]} == {"image.png"}

    url = presigned_get(bucket, key)
    res = requests.get(url)
    res.raise_for_status()
    assert res.content == bytes

    delete_index_bucket(index_with_bucket)
