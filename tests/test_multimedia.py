from io import BytesIO
import os
import requests
from amcat4 import multimedia


def test_upload_get_multimedia(minio, index):
    assert list(multimedia.list_multimedia_objects(index)) == []
    multimedia.add_multimedia_object(index, "test", b"bytes")
    assert {o["key"] for o in multimedia.list_multimedia_objects(index)} == {"test"}


def test_presigned_form(minio, index):
    assert list(multimedia.list_multimedia_objects(index)) == []
    bytes = os.urandom(32)
    key = "image.png"
    url, form_data = multimedia.presigned_post(index, "")
    res = requests.post(
        url=url,
        data={"key": key, **form_data},
        files={"file": BytesIO(bytes)},
    )
    res.raise_for_status()
    assert {o["key"] for o in multimedia.list_multimedia_objects(index)} == {"image.png"}

    url = multimedia.presigned_get(index, key)
    res = requests.get(url)
    res.raise_for_status()
    assert res.content == bytes
