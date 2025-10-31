from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from mypy_boto3_s3.type_defs import CommonPrefixTypeDef, ObjectTypeDef

from amcat4.api.auth import authenticated_user
from amcat4.models import Roles, User
from amcat4.multimedia import multimedia
from amcat4.systemdata.roles import HTTPException_if_not_project_index_role

app_multimedia = APIRouter(prefix="/index/{ix}/multimedia", tags=["multimedia"])

## TODO reimplement these endpoints


@app_multimedia.get("/presigned_get")
def presigned_get(ix: str, key: str, user: User = Depends(authenticated_user)):
    HTTPException_if_not_project_index_role(user, ix, Roles.READER)

    try:
        url = multimedia.presigned_get(ix, key)
        obj = multimedia.stat_multimedia_object(ix, key)
        return dict(url=url, content_type=(obj["ContentType"],), size=obj["ContentLength"])
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return None


@app_multimedia.get("/presigned_post")
def presigned_post(ix: str, user: User = Depends(authenticated_user)):
    HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
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
    metadata=False,
    user: User = Depends(authenticated_user),
):
    recursive = str(recursive).lower() == "true"
    metadata = str(metadata).lower() == "true"
    presigned_get = str(presigned_get).lower() == "true"

    def process(obj: ObjectTypeDef | CommonPrefixTypeDef):
        if "Prefix" in obj:
            return {
                "key": obj["Prefix"],
                "is_dir": True,
            }

        if "Key" in obj:
            key = obj["Key"]
            result: dict[str, object] = dict(
                key=key,
                is_dir=False,
                last_modified=obj.get("LastModified"),
                size=obj.get("Size"),
            )

            if metadata:
                o = multimedia.stat_multimedia_object(ix, key)
                result["metadata"] = o["Metadata"]
                result["content_type"] = o["ContentType"]

            if presigned_get is True:
                if n > 10:
                    raise ValueError("Cannot provide presigned_get for more than 10 objects")
                result["presigned_get"] = multimedia.presigned_get(ix, key)

            return result

        raise ValueError("Unknown object type")

    HTTPException_if_not_project_index_role(user, ix, Roles.READER)

    objects = multimedia.list_multimedia_objects(ix, prefix, start_after, recursive)
    return [process(obj) for obj in itertools.islice(objects, n)]
    return None
