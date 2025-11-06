from io import BytesIO
import os
import pytest
import requests
from amcat4.objectstorage.multimedia import delete_project_multimedia
from amcat4.objectstorage.s3bucket import (
    add_s3_object,
    get_bucket,
    list_s3_objects,
    presigned_get,
    presigned_post,
    s3_enabled,
)

if not s3_enabled():
    pytest.skip("S3 not configured, skipping multimedia tests", allow_module_level=True)


def test_upload_get_s3(index):
    bucket = get_bucket("multimedia")
    prefix = f"{index}/"
    assert list_s3_objects(bucket, prefix=prefix) == {"items": [], "next_page_token": None, "is_last_page": True}
    add_s3_object(bucket, prefix + "test", b"bytes")
    assert {o["key"] for o in list_s3_objects(bucket, prefix=prefix)["items"]} == {"amcat4_unittest_index/test"}


def test_presigned_form(index):
    bucket = get_bucket("multimedia")
    prefix = f"{index}/"

    assert list_s3_objects(bucket, prefix=prefix) == {"items": [], "next_page_token": None, "is_last_page": True}
    bytes = os.urandom(32)
    key = prefix + "doc/image"

    url, form_data = presigned_post(bucket, key=key)

    res = requests.post(
        url=url,
        data={"Content-Type": "image/png", **form_data},
        files={"file": ("filename_is_fixed.haha", BytesIO(bytes))},
        # allow_redirects=False,
    )
    res.raise_for_status()
    assert {o["key"] for o in list_s3_objects(bucket, prefix=prefix)["items"]} == {"amcat4_unittest_index/doc/image"}

    url = presigned_get(bucket, key)
    res = requests.get(url)
    res.raise_for_status()
    assert res.content == bytes

    delete_project_multimedia(index)
