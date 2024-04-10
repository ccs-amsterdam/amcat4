import itertools
from typing import Optional
from fastapi import APIRouter, Depends

from amcat4 import index, multimedia
from amcat4.api.auth import authenticated_user, check_role


app_multimedia = APIRouter(prefix="/index/{ix}/multimedia", tags=["multimedia"])


@app_multimedia.get("/presigned_get")
def presigned_get(ix: str, key: str, user: str = Depends(authenticated_user)):
    check_role(user, index.Role.READER, ix)
    url = multimedia.presigned_get(ix, key)
    return dict(url=url)


@app_multimedia.get("/presigned_post")
def presigned_post(ix: str, user: str = Depends(authenticated_user)):
    check_role(user, index.Role.WRITER, ix)
    url, form_data = multimedia.presigned_post(ix)
    return dict(url=url, form_data=form_data)


@app_multimedia.get("/list")
def list_multimedia(
    ix: str,
    n: int = 10,
    prefix: Optional[str] = None,
    start_after: Optional[str] = None,
    recursive=False,
    presigned_get=False,
    user: str = Depends(authenticated_user),
):
    def process(obj):
        result = dict(key=obj.object_name)
        if presigned_get:
            result["presigned_get"] = multimedia.presigned_get(ix, obj.object_name)
        return result

    check_role(user, index.Role.READER, ix)
    objects = multimedia.list_multimedia_objects(ix, prefix, start_after, recursive)
    return [process(obj) for obj in itertools.islice(objects, n)]
