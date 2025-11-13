from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from amcat4.api.auth import authenticated_user
from amcat4.models import ObjectStorage, RegisterObject, Roles, User
from amcat4.objectstorage.multimedia import (
    get_multimedia_meta,
    presigned_multimedia_get,
    presigned_multimedia_post,
    refresh_multimedia_register,
)
from amcat4.systemdata.fields import HTTPException_if_invalid_or_unauthorized_field
from amcat4.systemdata.objectstorage import list_objects, register_objects
from amcat4.systemdata.roles import HTTPException_if_not_project_index_role

app_multimedia = APIRouter(prefix="", tags=["multimedia"])

## TODO: make MAX_BYTES a project setting
## Server Devs should be able to set default project limits (like es and s3 size),
## and should be able to change them later. (and via requests)
## Project admins cannot change these limits, only server devs can.
S3_MAX_BYTES_PER_PROJECT = 1 * 1024 * 1024 * 1024  # 1 GB

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


class PresignedPost(BaseModel):
    filepath: str = Field(description="Name of the file (set by default in the presigned POST form)")
    url: str = Field(description="The URL to POST the file to")
    form_data: dict[str, str] = Field(description="The form data to include in the POST request")


class UploadMultimediaResponse(BaseModel):
    skipped: int = Field(description="Number of files that were skipped because they already existed with the same size")
    new_total_size: int = Field(description="New total size of all multimedia files in the project after upload")
    max_total_size: int = Field(description="Maximum allowed total size of all multimedia files in the project")
    presigned_posts: list[PresignedPost] = Field(description="List of presigned POST details for uploading the files")


class ListMultimediaResponse(BaseModel):
    scroll_id: str | None = Field(description="Scroll ID to continue listing from")
    objects: list[ObjectStorage] = Field(description="List of registered multimedia objects")


@app_multimedia.post("/index/{ix}/multimedia/upload")
def upload_multimedia(
    ix: str,
    body: Annotated[list[RegisterObject], Body(...)],
    user: User = Depends(authenticated_user),
):
    """
    Upload a multimedia file. This is a two step process.

    - First you call this endpoint to register the upload for a specific document field with a given size.
    - You then receive a presigned POST url that you can use to upload the file.

    If a file already exists, it will be overwritten.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)

    max_size = S3_MAX_BYTES_PER_PROJECT
    new_total_size, add_objects = register_objects(ix, body, max_bytes=max_size)

    presigned_posts: list[PresignedPost] = []
    for obj in add_objects:
        url, form = presigned_multimedia_post(ix, obj)
        presigned_posts.append(
            PresignedPost(
                filepath=obj.filepath,
                url=url,
                form_data=form,
            )
        )

    return UploadMultimediaResponse(
        skipped=len(body) - len(add_objects),
        new_total_size=new_total_size,
        max_total_size=max_size,
        presigned_posts=presigned_posts,
    )


@app_multimedia.get("/index/{ix}/multimedia")
def list_multimedia(
    ix: str,
    page_size: int = Query(1000, description="Max number of objects to return per page"),
    directory: str | None = Query(None, description="Path of the directory to list objects from"),
    search: str | None = Query(None, description="Search term to filter multimedia objects"),
    recursive: bool = Query(default=False, description="If false, only list objects in the directory for the given prefix"),
    scroll_id: str | None = Query(None, description="Scroll ID to continue listing from"),
    user: User = Depends(authenticated_user),
) -> ListMultimediaResponse:
    """
    List all registered multimedia objects.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.READER)

    new_scroll_id, objects = list_objects(ix, page_size, directory, search, recursive, scroll_id)

    return ListMultimediaResponse(scroll_id=new_scroll_id, objects=objects)


# This would now be replaced by using the s3 registry (objectstorage system index).
# We could also provide a way to list the actual s3 objects, but not sure if needed,
# and it might be good the keep the s3 part purely internal, so we can also swap it out later.

# @app_multimedia.get("/index/{ix}/multimedia/bucket")
# def list_multimedia_bucket(
#     ix: str,
#     page_size: int = Query(1000, description="Max number of objects to return per page"),
#     next_page_token: str | None = Query(None, description="Token to continue listing from"),
#     directory: str | None = Query(None, description="Path of the directory to list objects from"),
#     recursive: bool = Query(False, description="If false, only list objects in the directory for the given prefix"),
#     user: User = Depends(authenticated_user),
# ):
#     """
#     List all multimedia objects in an index's S3 bucket.
#     """
#     HTTPException_if_not_project_index_role(user, ix, Roles.READER)

#     try:
#         return list_multimedia_bucket(ix, page_size, next_page_token, directory, recursive)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


@app_multimedia.get("/index/{ix}/multimedia/refresh")
def refresh_multimedia(
    ix: str,
    field: str | None = Query(None, description="Limit refresh to specific elastic field"),
    user: User = Depends(authenticated_user),
) -> dict:
    HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
    return refresh_multimedia_register(ix, field)


@app_multimedia.get("/index/{ix}/multimedia/get/{field}/{filepath:path}")
def multimedia_get_gatekeeper(
    ix: str,
    field: Annotated[str, Path(description="The name of the elastic field containing the multimedia object")],
    filepath: Annotated[str, Path(description="The filepath of the multimedia object")],
    cache: Annotated[
        str | None,
        Query(
            description="Used for browser caching (do not set yourself)",
        ),
    ] = None,
    max_size: Annotated[
        int | None,
        Query(
            description="Optional maximum size of the multimedia object in bytes. If the object exceeds this size, a 413 error will be returned.",
        ),
    ] = None,
    skip_mime_check: Annotated[
        bool,
        Query(
            description="By default, the server checks the mime type of the multimedia object before serving it. Set this to true to skip this check (better performance, but need to trust the stored mime type).",
        ),
    ] = True,
    user: User = Depends(authenticated_user),
):
    """
    Gatekeeper endpoint for multimedia GET requests.

    When viewed in browser, the ?cache=true parameter should be set. This triggers a self redirect with a unique cache id for the
    current version of the multimedia object, allowing the browser to cache the object.
    """

    # We skip these checks if cache is set to a specific etag value, because this should only happen if
    # the browser already did the initial request with cache=true. Note that this is only possible for
    # checks that protect the user, and not checks that protect the server (like unauthorized field)
    if cache is None or cache == "true":
        meta = get_multimedia_meta(ix, field, filepath, read_mimetype=not skip_mime_check)

        if not meta:
            HTTPException_if_invalid_or_unauthorized_field(ix, field, user)
            raise HTTPException(status_code=404, detail="Multimedia object not found")

        if not skip_mime_check:
            if meta["real_content_type"] != meta["ext_content_type"]:
                HTTPException_if_invalid_or_unauthorized_field(ix, field, user)
                raise HTTPException(
                    status_code=400,
                    detail=f"The multimedia file extension {meta['ext_content_type']} does not match its real content type {meta['real_content_type']}",
                )

        if max_size is not None and meta["size"] > max_size:
            HTTPException_if_invalid_or_unauthorized_field(ix, field, user)
            raise HTTPException(status_code=413, detail="Multimedia object exceeds maximum allowed size")

        if cache == "true":
            return RedirectResponse(
                url=f"/index/{ix}/multimedia/{field}/{filepath}?cache={meta['etag']}",
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            )

    HTTPException_if_invalid_or_unauthorized_field(ix, field, user)

    set_immutable_cache = cache is not None and cache != "true"
    presigned_url = presigned_multimedia_get(ix, field, filepath, immutable_cache=set_immutable_cache)
    return RedirectResponse(url=presigned_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
