import itertools
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from mypy_boto3_s3.type_defs import CommonPrefixTypeDef, ObjectTypeDef

from amcat4.api.auth import authenticated_user
from amcat4.models import Roles, User
from amcat4.multimedia import objectstorage
from amcat4.systemdata.roles import HTTPException_if_not_project_index_role

app_multimedia = APIRouter(prefix="", tags=["multimedia"])

## TODO reimplement these endpoints


@app_multimedia.get("/index/{ix}/multimedia/presigned_get")
def multimedia_get(ix: str, key: str, user: User = Depends(authenticated_user)):
    """
    Redirect to a presigned URL for getting a multimedia object.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.READER)

    return None


@app_multimedia.get("/index/{ix}/multimedia/presigned_get")
def presigned_get(ix: str, key: str, user: User = Depends(authenticated_user)):
    HTTPException_if_not_project_index_role(user, ix, Roles.READER)

    try:
        bucket = objectstorage.get_bucket(ix)
        url = objectstorage.presigned_get(bucket, key)
        obj = objectstorage.stat_s3_object(bucket, key)
        return dict(url=url, content_type=(obj["ContentType"],), size=obj["ContentLength"])
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return None


@app_multimedia.get("/index/{ix}/multimedia/presigned_post")
def presigned_post(ix: str, user: User = Depends(authenticated_user)):
    HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
    bucket = objectstorage.get_bucket(ix)
    url, form_data = objectstorage.presigned_post(bucket)
    return dict(url=url, form_data=form_data)


@app_multimedia.get("/index/{ix}/multimedia/list")
def list_multimedia(
    ix: str,
    n: int = Query(50, description="Number of objects to return"),
    prefix: str | None = Query(None, description="Only list objects with this prefix"),
    next_page_token: str | None = Query(None, description="Token to continue listing from"),
    recursive: bool = Query(False, description="Whether to list objects recursively"),
    presigned_get: bool = Query(False, description="Whether to include presigned GET URLs"),
    user: User = Depends(authenticated_user),
):
    recursive = str(recursive).lower() == "true"
    presigned_get = str(presigned_get).lower() == "true"

    if presigned_get is True and n > 50:
        raise ValueError("Cannot provide presigned_get for more than 50 objects at a time")

    HTTPException_if_not_project_index_role(user, ix, Roles.READER)

    bucket = objectstorage.get_bucket(ix)
    return objectstorage.list_s3_objects(bucket, prefix, n, next_page_token, recursive, presigned_get)
