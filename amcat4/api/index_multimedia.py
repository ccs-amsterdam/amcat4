from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from amcat4.api.auth import authenticated_user
from amcat4.models import ObjectStorage, RegisterObject, Roles, User
from amcat4.objectstorage.multimedia import (
    delete_multimedia_by_key,
    get_multimedia_meta,
    presigned_multimedia_get,
    presigned_multimedia_post,
    refresh_multimedia_register,
)
from amcat4.systemdata.fields import HTTPException_if_invalid_or_unauthorized_multimedia_field
from amcat4.systemdata.objectstorage import list_objects, register_objects
from amcat4.systemdata.roles import HTTPException_if_not_project_index_role

app_multimedia = APIRouter(prefix="", tags=["multimedia"])

## TODO: make MAX_BYTES a project setting
## Server Devs should be able to set default project limits (like es and s3 size),
## and should be able to change them later. (and via requests)
## Project admins cannot change these limits, only server devs can.
S3_MAX_BYTES_PER_PROJECT = 1 * 1024 * 1024 * 1024  # 1 GB


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


@app_multimedia.post("/index/{ix}/multimedia/upload/{field}")
async def upload_multimedia(
    ix: str,
    field: str,
    body: Annotated[list[RegisterObject], Body(...)],
    user: User = Depends(authenticated_user),
):
    """
    Upload a multimedia file. This is a two step process.

    - First you call this endpoint to register the upload for a specific document field with a given size.
    - You then receive a presigned POST url that you can use to upload the file.

    If a file already exists, it will be overwritten.
    """
    await HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)

    max_size = S3_MAX_BYTES_PER_PROJECT
    new_total_size, add_objects = await register_objects(ix, field, body, max_bytes=max_size)

    presigned_posts: list[PresignedPost] = []
    for obj in add_objects:
        url, form = await presigned_multimedia_post(ix, obj)
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


@app_multimedia.post("/index/{ix}/multimedia/{field}")
async def delete_multimedia(
    ix: str,
    field: str,
    filepaths: list[str] = Body(
        ..., max_length=100, description="List of filepaths to delete from the multimedia register and storage"
    ),
    user: User = Depends(authenticated_user),
):
    """
    Delete a multimedia object from the register and the storage.
    """
    await HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
    await delete_multimedia_by_key(ix, field, filepaths)


@app_multimedia.get("/index/{ix}/multimedia")
async def list_multimedia(
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
    await HTTPException_if_not_project_index_role(user, ix, Roles.READER)

    try:
        new_scroll_id, objects = await list_objects(ix, page_size, directory, search, recursive, scroll_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return ListMultimediaResponse(scroll_id=new_scroll_id, objects=objects)


# This is now be replaced by using the s3 registry (objectstorage system index).
# We could also provide a way to list the actual s3 objects, but not sure if needed,
# and it might be good the keep the s3 part purely internal, so we can also swap it out later.

# @app_multimedia.get("/index/{ix}/multimedia/bucket")
# async def list_multimedia_bucket(
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
#     await HTTPException_if_not_project_index_role(user, ix, Roles.READER)

#     try:
#         return await list_multimedia_bucket(ix, page_size, next_page_token, directory, recursive)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


@app_multimedia.get("/index/{ix}/multimedia/refresh")
async def refresh_multimedia(
    ix: str,
    field: str | None = Query(default=None, description="Limit refresh to specific elastic field"),
    user: User = Depends(authenticated_user),
) -> dict:
    await HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
    return await refresh_multimedia_register(ix, field)


@app_multimedia.get("/index/{ix}/multimedia/get/{field}/{filepath:path}")
async def multimedia_get_gatekeeper(
    ix: str,
    field: Annotated[str, Path(description="The name of the elastic field containing the multimedia object")],
    filepath: Annotated[str, Path(description="The filepath of the multimedia object")],
    cache: Annotated[
        bool,
        Query(
            description="Only use in browser. If true, the server will respond with a redirect to a unique cached version of the multimedia object, allowing the browser to cache it. If set to a specific etag value, the server will serve that specific version of the multimedia object with immutable caching.",
        ),
    ] = False,
    max_size: Annotated[
        int | None,
        Query(
            description="Optional maximum size of the multimedia object in bytes. If the object exceeds this size, a 413 error will be returned.",
        ),
    ] = None,
    skip_mime_check: Annotated[
        bool | None,
        Query(
            description="By default, the server checks the mime type of the multimedia object before serving it. Set this to true to skip this check (better performance, but need to trust the stored mime type).",
        ),
    ] = False,
    etag: Annotated[
        str | None,
        Query(
            include_in_schema=False,
        ),
    ] = None,
    version_id: Annotated[
        str | None,
        Query(
            include_in_schema=False,
        ),
    ] = None,
    user: User = Depends(authenticated_user),
):
    """
    Gatekeeper endpoint for multimedia GET requests.

    When viewed in browser, the ?cache=true parameter should be set. This triggers a self redirect with a unique cache id for the
    current version of the multimedia object, allowing the browser to cache the object.
    """
    if etag:
        # If an is given, we assume that all checks EXCEPT FOR AUTHORIZATION have already
        # been done, and that we can cache the redirected response from s3 indefinitely.
        await HTTPException_if_invalid_or_unauthorized_multimedia_field(ix, field, user)
        presigned_url = await presigned_multimedia_get(ix, field, filepath, version_id=version_id, immutable_cache=True)
        return RedirectResponse(url=presigned_url, status_code=status.HTTP_303_SEE_OTHER)

    meta = await get_multimedia_meta(ix, field, filepath, read_mimetype=not skip_mime_check)

    if not meta:
        await HTTPException_if_invalid_or_unauthorized_multimedia_field(ix, field, user)
        raise HTTPException(status_code=404, detail="Multimedia object not found")

    if not skip_mime_check and meta["real_content_type"] != meta["content_type"]:
        await HTTPException_if_invalid_or_unauthorized_multimedia_field(ix, field, user)
        raise HTTPException(
            status_code=400,
            detail=f"The multimedia file extension {meta['content_type']} does not match its real content type {meta['real_content_type']}",
        )

    if max_size is not None and meta["size"] > max_size:
        await HTTPException_if_invalid_or_unauthorized_multimedia_field(ix, field, user)
        raise HTTPException(status_code=413, detail="Multimedia object exceeds maximum allowed size")

    if cache:
        ## If cache is true, we redirect to this same endpoint with the version_id set,
        ## so that the browser can cache the unique version of this object.
        return RedirectResponse(
            url=f"/index/{ix}/multimedia/{field}/{filepath}?version_id={meta['etag']}",
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        )

    await HTTPException_if_invalid_or_unauthorized_multimedia_field(ix, field, user)
    presigned_url = await presigned_multimedia_get(ix, field, filepath, version_id=meta["version_id"], immutable_cache=False)
    return RedirectResponse(url=presigned_url, status_code=status.HTTP_303_SEE_OTHER)
