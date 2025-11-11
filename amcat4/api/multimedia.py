import hashlib
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Path, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from amcat4.api.auth import authenticated_user
from amcat4.elastic.util import es_upsert
from amcat4.models import Roles, User
from amcat4.objectstorage import s3bucket
from amcat4.objectstorage.multimedia import (
    get_multimedia_meta,
    presigned_multimedia_get,
    presigned_multimedia_post,
    update_multimedia_field,
)
from amcat4.projects.documents import fetch_document
from amcat4.systemdata.fields import HTTPException_if_invalid_multimedia_field
from amcat4.systemdata.roles import HTTPException_if_not_project_index_role

app_multimedia = APIRouter(prefix="", tags=["multimedia"])


class UploadPostBody(BaseModel):
    field: str = Field(description="The name of the elastic field to upload the multimedia object to")
    filename: str = Field(description="The original filename of the multimedia object. Can include directories.")
    size: int = Field(description="The exact (!) size of the multimedia file in bytes")


## TODO:
#
# ALTERNATIVE APPROACH:
# - Write S3 files to pending_multimedia bucket
# - On refresh, loop over all pending files for this bucket, write them to elastic and move to multimedia bucket
# - DONT do the redirect refresh per upload, just do it once at the end.
# -
#

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


@app_multimedia.post("/index/{ix}/multimedia/upload")
def upload_multimedia(
    ix: str,
    body: Annotated[UploadPostBody, Body(...)],
    user: User = Depends(authenticated_user),
    request=Request,
):
    """
    Upload a multimedia file. This is a two step process.

    - First you call this endpoint to register the upload for a specific document field with a given size.
    - You then receive a presigned POST url that you can use to upload the file.

    If a file already exists, it will be overwritten.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)

    # field_types: dict[str, str] = {}

    current = fetch_document(ix, body.document, source_includes=["field"]).get(body.field)
    if current and current.get("hash") == body.hash and current.get("size") == body.size:
        current_s3 = get_multimedia_meta(ix, body.document, body.field)
        if current_s3:
            raise HTTPException(status_code=409, detail="Multimedia file already exists")
    else:
        update_multimedia_field(ix, body.document, body.field, body.hash, body.size)

    return presigned_multimedia_post(ix, body.document, body.field, body.size)


@app_multimedia.get("/index/{ix}/multimedia")
def list_multimedia(
    ix: str,
    n: int = Query(50, description="Number of objects to return"),
    next_page_token: str | None = Query(None, description="Token to continue listing from"),
    presigned_get: bool = Query(False, description="Whether to include presigned GET URLs"),
    user: User = Depends(authenticated_user),
):
    """
    List all multimedia objects in an index's S3 bucket.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.READER)
    presigned_get = str(presigned_get).lower() == "true"

    if presigned_get is True and n > 50:
        raise ValueError("Cannot provide presigned_get for more than 50 objects at a time")

    bucket = s3bucket.get_bucket("multimedia")
    prefix = f"{ix}/"

    try:
        res = s3bucket.list_s3_objects(bucket, prefix, n, next_page_token, recursive=True, presigned=presigned_get)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app_multimedia.get("/index/{ix}/multimedia/{doc}/{field}/{etag}")
def multimedia_get_gatekeeper(
    ix: str,
    doc: Annotated[str, Path(description="The document id containing the multimedia object")],
    field: Annotated[str, Path(description="The name of the elastic field containing the multimedia object")],
    cache: Annotated[
        str | None,
        Query(
            description="Optional unique id for browser caching. If provided, the response will be cached immutably.",
        ),
    ],
    user: User = Depends(authenticated_user),
):
    """
    Gatekeeper endpoint for multimedia GET requests. Redirects to a presigned S3 URL.
    """
    HTTPException_if_invalid_multimedia_field(ix, field, user)

    # meta = get_multimedia_meta(ix, doc, field)
    # if not meta:
    #     raise HTTPException(status_code=404, detail="Multimedia object not found")
    # current_etag = meta["ETag"].strip('"')
    # if not hash == current_etag:
    #     size = meta["ContentLength"]
    #     update_multimedia_field(ix, doc, field, current_etag, size)
    #     return RedirectResponse(
    #         url=f"/index/{ix}/multimedia/{doc}/{field}/{current_etag}",
    #         status_code=status.HTTP_308_PERMANENT_REDIRECT,
    #         headers={"Cache-Control": "public, max-age=31536000"},
    #     )

    presigned_url = presigned_multimedia_get(ix, doc, field, immutable_cache=id is not None)
    return RedirectResponse(url=presigned_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
