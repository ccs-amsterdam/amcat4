from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Header, Path, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from amcat4.api.auth import authenticated_user
from amcat4.models import Roles, User
from amcat4.objectstorage import s3bucket
from amcat4.objectstorage.multimedia import get_multimedia_etag, presigned_multimedia_get, presigned_multimedia_post
from amcat4.systemdata.fields import HTTPException_if_invalid_multimedia_field
from amcat4.systemdata.roles import HTTPException_if_not_project_index_role

app_multimedia = APIRouter(prefix="", tags=["multimedia"])

## TODO reimplement these endpoints


# @app_multimedia.get("/index/{ix}/multimedia/presigned_get")
# def presigned_get(ix: str, key: str, user: User = Depends(authenticated_user)):
#     HTTPException_if_not_project_index_role(user, ix, Roles.READER)

#     try:
#         bucket = s3bucket.bucket_name(ix)
#         url = s3bucket.presigned_get(bucket, key)
#         obj = s3bucket.stat_s3_object(bucket, key)
#         return dict(url=url, content_type=(obj["ContentType"],), size=obj["ContentLength"])
#     except Exception as e:
#         raise HTTPException(status_code=404, detail=str(e))
#     return None

class PresignUploadBody(BaseModel):
    links: list[str] = Field(description="Links to multimedia objects")
    field: str | None = Field(None, description="Optionally, only look in a specific field")


@app_multimedia.post(f"/index/{ix}/multimedia/presign_upload")
def presigned_post(ix: str,
    body
    user: User = Depends(authenticated_user)):
    """
    Upload a list of multimedia file links (e.g., [folder/image.png, folder/subfolder/video.mp4]),
    and receive presigned POST URLs for uploading the file to a document field that matches
    the link.

    The link must match the
    link value in one of the multimedia fields in the index.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)

    return presigned_multimedia_post(ix, doc, field, id)


@app_multimedia.post("/index/{ix}/multimedia/presign_upload/{doc}/{field}")
def presigned_post(ix: str,
    doc: str,
    field: str,
    user: User = Depends(authenticated_user)):
    """
    Get a presigned POST URL for uploading a multimedia object to a specific document field.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)

    return presigned_multimedia_post(ix, doc, field, id)


@app_multimedia.get("/index/{ix}/multimedia")
def list_multimedia(
    ix: str,
    n: int = Query(50, description="Number of objects to return"),
    prefix: str | None = Query(None, description="Only list objects with this prefix"),
    next_page_token: str | None = Query(None, description="Token to continue listing from"),
    recursive: bool = Query(False, description="Whether to list objects recursively"),
    presigned_get: bool = Query(False, description="Whether to include presigned GET URLs"),
    user: User = Depends(authenticated_user),
):
    """
    List all multimedia objects in an index's S3 bucket.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.READER)
    base_prefix = "multimedia/"

    prefix = f"{base_prefix}{prefix or ''}"

    recursive = str(recursive).lower() == "true"
    presigned_get = str(presigned_get).lower() == "true"

    if presigned_get is True and n > 50:
        raise ValueError("Cannot provide presigned_get for more than 50 objects at a time")

    bucket = s3bucket.bucket_name(ix)
    try:
        res = s3bucket.list_s3_objects(bucket, prefix, n, next_page_token, recursive, presigned_get)
        for item in res["items"]:
            item["key"] = item["key"].removeprefix(base_prefix)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app_multimedia.get("/index/{ix}/multimedia/{doc}/{field}/{id}")
def multimedia_get_gatekeeper(
    ix: str,
    doc: Annotated[str, Path(description="The document id containing the multimedia object")],
    field: Annotated[str, Path(description="The name of the elastic field containing the multimedia object")],
    path: Annotated[str, Path(description="Path to the multimedia object within the field")],
    v: str | None = Query(
        None, description="A unique version id (like the S3 etag) can be included in query for immutable caching."
    ),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
    user: User = Depends(authenticated_user),
):
    """
    Gatekeeper endpoint for multimedia GET requests. Redirects to a presigned S3 URL.

    Uses two caching flows:
    1. eTag based caching: if the client provides a fresh If-None-Match header, return 304
    2. if a version (v) is provided in the query, we set an immutable caching policy
    """
    # note that both caching flows ignore auth for speed. The only risk is that a user can see
    # a browser cached version of a file they are not allowed to see (anymore).

    # eTag flow
    if if_none_match:
        current_etag = get_multimedia_etag(ix, field, path)
        if if_none_match.strip('"') == current_etag:
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": f'"{current_etag}"'})

    # presigned url flow with immutable caching if version (v) is given
    HTTPException_if_invalid_multimedia_field(ix, field, user)
    presigned_url = presigned_multimedia_get(ix, field, path, immutable_cache=v is not None)
    return RedirectResponse(url=presigned_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
