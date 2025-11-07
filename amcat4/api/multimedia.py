from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response, status
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
    refresh_index_multimedia,
    update_multimedia_field,
)
from amcat4.projects.documents import fetch_document
from amcat4.systemdata.fields import HTTPException_if_invalid_multimedia_field
from amcat4.systemdata.roles import HTTPException_if_not_project_index_role

app_multimedia = APIRouter(prefix="", tags=["multimedia"])

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


@app_multimedia.get("/index/{ix}/multimedia/upload/{doc}/{field}")
def upload_multimedia(ix: str, doc: str, field: str, user: User = Depends(authenticated_user), request=Request):
    """
    Upload a multimedia file. This is a three step process.

    - First you call this endpoint to get a presigned POST URL. The document/field is now marked as PENDING,
    and you receive a URL and form data to upload the file to S3.
    - You then upload the file to S3 using that URL and form data.
    - Finally, you call the multimedia/refresh endpoint to update the document references.

    If you want to upload many files, you do not need to refresh after each upload, you can do it once at the end.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)

    # base_url = str(request.base_url).rstrip("/")
    # redirect_path = f"/index/{ix}/multimedia/{doc}/{field}/refresh"
    # redirect_url = f"{base_url}{redirect_path}"

    redirect_url = f"/index/{ix}/multimedia/{doc}/{field}/refresh"
    return presigned_multimedia_post(ix, doc, field, redirect=redirect_url)


@app_multimedia.get("/index/{ix}/multimedia/{doc}/{field}/refresh")
def refresh_multimedia_field(ix: str, doc: str, field: str) -> None:
    """
    This endpoint is automatically redirected to after uploading a multimedia file.
    It updates the references to the uploaded file in the elasticsearch documents.

    This is a public endpoint so that S3 can call it.
    """
    print("hieeer")
    meta = get_multimedia_meta(ix, doc, field)
    if meta:
        update = {field: {"etag": meta["ETag"], "size": meta["ContentLength"]}}
        es_upsert(ix, doc, update, refresh=True)


@app_multimedia.get("/index/{ix}/multimedia/refresh")
def refresh_multimedia(ix: str, user: User = Depends(authenticated_user)):
    """
    After uploading multimedia files (with multimedia/presign_upload), call this endpoint to update
    the references to these files in the elasticsearch documents.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
    return refresh_index_multimedia(ix)


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
    etag: Annotated[str, Path(description="etag of the multimedia object")],
    if_none_match: str | None = Header(None, alias="If-None-Match"),
    user: User = Depends(authenticated_user),
):
    """
    Gatekeeper endpoint for multimedia GET requests. Redirects to a presigned S3 URL.
    """
    HTTPException_if_invalid_multimedia_field(ix, field, user)

    # TODO: discuss whether we need this.
    # - We only use the etag for cache busting, so we don't actually care if an invalid etag was used
    # - THe update_multimedia_field is just a safety net in case an s3 update was not properly registered,
    #   but if this is a real issue we need a better way to ensure consistency anyway.
    meta = get_multimedia_meta(ix, doc, field)
    if not meta:
        raise HTTPException(status_code=404, detail="Multimedia object not found")
    current_etag = meta["ETag"].strip('"')
    if not etag == current_etag:
        size = meta["ContentLength"]
        update_multimedia_field(ix, doc, field, current_etag, size)
        return RedirectResponse(
            url=f"/index/{ix}/multimedia/{doc}/{field}/{current_etag}",
            status_code=status.HTTP_308_PERMANENT_REDIRECT,
            headers={"Cache-Control": "public, max-age=31536000"},
        )

    presigned_url = presigned_multimedia_get(ix, doc, field, immutable_cache=True)
    return RedirectResponse(url=presigned_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
