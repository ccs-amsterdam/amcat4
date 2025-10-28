from typing import Optional
from fastapi import APIRouter, Depends

from amcat4.api.auth import authenticated_user

app_multimedia = APIRouter(prefix="/index/{ix}/multimedia", tags=["multimedia"])

## TODO reimplement these endpoints


@app_multimedia.get("/presigned_get")
def presigned_get(ix: str, key: str, user: str = Depends(authenticated_user)):
    # check_role(user, index.Role.READER, ix)
    # try:
    #     url = multimedia.presigned_get(ix, key)
    #     obj = multimedia.stat_multimedia_object(ix, key)
    #     return dict(url=url, content_type=(obj.content_type,), size=obj.size)
    # except S3Error as e:
    #     if e.code == "NoSuchKey":
    #         raise HTTPException(status_code=404, detail=f"multimedia file {key} not found")
    #     raise HTTPException(status_code=404, detail=e.message)
    return None


@app_multimedia.get("/presigned_post")
def presigned_post(ix: str, user: str = Depends(authenticated_user)):
    # check_role(user, index.Role.WRITER, ix)
    # url, form_data = multimedia.presigned_post(ix)
    # return dict(url=url, form_data=form_data)
    return None


@app_multimedia.get("/list")
def list_multimedia(
    ix: str,
    n: int = 10,
    prefix: Optional[str] = None,
    start_after: Optional[str] = None,
    recursive=False,
    presigned_get=False,
    metadata=False,
    user: str = Depends(authenticated_user),
):
    # recursive = str(recursive).lower() == "true"
    # metadata = str(metadata).lower() == "true"
    # presigned_get = str(presigned_get).lower() == "true"

    # def process(obj: Object):
    #     if metadata and (not obj.is_dir) and obj.object_name:
    #         obj = multimedia.stat_multimedia_object(ix, obj.object_name)
    #     result: dict[str, object] = dict(
    #         key=obj.object_name,
    #         is_dir=obj.is_dir,
    #         last_modified=obj.last_modified,
    #         size=obj.size,
    #     )
    #     if metadata:
    #         result["metadata"] = (obj.metadata,)
    #         result["content_type"] = (obj.content_type,)

    #     if presigned_get is True and not obj.is_dir:
    #         if n > 10:
    #             raise ValueError("Cannot provide presigned_get for more than 10 objects")
    #         result["presigned_get"] = multimedia.presigned_get(ix, obj.object_name)
    #     return result

    # check_role(user, index.Role.READER, ix)
    # objects = multimedia.list_multimedia_objects(ix, prefix, start_after, recursive)
    # return [process(obj) for obj in itertools.islice(objects, n)]
    return None
