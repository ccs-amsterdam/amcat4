"""API Endpoints for document and index management."""

import base64
from datetime import datetime
from typing import Annotated

from elastic_transport import ApiError
from elasticsearch import NotFoundError
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, Field


from amcat4.projects.index import (
    IndexAlreadyExists,
    IndexDoesNotExist,
    create_project_index,
    delete_project_index,
    index_size_in_bytes,
    list_user_project_indices,
    refresh_index,
    update_project_index,
)
from amcat4.api.auth import authenticated_user
from amcat4.api.index_query import FiltersType, QueriesType, _standardize_filters, _standardize_queries
from amcat4.models import (
    ContactInfo,
    GuestRole,
    IndexId,
    ProjectSettings,
    Role,
    RoleEmailPattern,
    Roles,
    User,
)
from amcat4.projects.query import reindex
from amcat4.multimedia.image_processing import create_image_from_url
from amcat4.systemdata.roles import (
    get_project_guest_role,
    get_user_project_role,
    HTTPException_if_not_project_index_role,
    HTTPException_if_not_server_role,
    set_project_guest_role,
)
from amcat4.systemdata.settings import get_project_image, get_project_settings

app_index = APIRouter(prefix="", tags=["index"])

# TODO: rename to projects and add deprecated index route
# app_projects = APIRouter(prefix="/projects", tags=["projects"])
# app_index_deprecated = APIRouter(prefix="/projects", tags=["projects"], deprecated=True)
#
# add both decorators to all functions, and register both routers


# REQUEST MODELS
class UpdateIndexBody(BaseModel):
    """Form to update an existing index."""

    name: str | None = Field(default=None, description="Name of the index")
    description: str | None = Field(default=None, description="Description of the index")
    guest_role: GuestRole | None = Field(default=None, description="Guest role for the index")
    folder: str | None = Field(default=None, description="Folder for the index")
    image_url: str | None = Field(default=None, description="Image URL for the index")
    contact: list[ContactInfo] | None = Field(default=None, description="Contact info for the index")


class CreateIndexBody(UpdateIndexBody):
    """Form to create a new index."""

    id: IndexId = Field(description="ID of the new index")


class ReindexBody(BaseModel):
    """Body for reindexing documents."""

    destination: str = Field(description="The destination index id")
    queries: QueriesType
    filters: FiltersType


# RESPONSE MODELS
class IndexListResponse(BaseModel):
    id: IndexId = Field(description="ID of the index")
    name: str | None = Field(description="Name of the index")
    description: str = Field(description="Description of the index")
    user_role: Role | None = Field(description="Role of the current user on this index")
    user_role_match: RoleEmailPattern | None = Field(description="Email pattern that determined the user role")
    archived: str | None = Field(description="Timestamp of when the index was archived, or null if not archived")
    folder: str | None = Field(description="Folder for the index")
    image_id: str | None = Field(description="Image ID for the index")


class IndexViewResponse(IndexListResponse):
    guest_role: GuestRole | None = Field(description="Guest role for the index")
    contact: list[ContactInfo] | None = Field(description="Contact info for the index")
    bytes: int = Field(description="Size of the index in bytes")


@app_index.get("/index/")
def index_list(
    show_all: Annotated[
        bool, Query(..., description="Also show indices user has no role on (requires ADMIN server role)")
    ] = False,
    user: User = Depends(authenticated_user),
) -> list[IndexListResponse]:
    """
    List indices from this server that the user has access to. Returns a list of dicts with index details, including the user role.
    Requires at least LISTER role on the index. If show_all is true, requires ADMIN server role and shows all indices.
    """
    if show_all:
        HTTPException_if_not_server_role(user, Roles.ADMIN)
    print(show_all)

    ix_list: list = []
    for ix, role in list_user_project_indices(user, show_all=show_all):
        ix_list.append(
            dict(
                id=ix.id,
                name=ix.name or "",
                user_role=role.role if role else None,
                user_role_match=role.email if role else None,
                description=ix.description or "",
                archived=ix.archived or "",
                folder=ix.folder or "",
                image_id=ix.image.id if ix.image else None,
            )
        )

    return ix_list


@app_index.post("/index/", status_code=status.HTTP_201_CREATED)
def create_index(
    body: Annotated[CreateIndexBody, Body(...)],
    user: User = Depends(authenticated_user),
):
    """
    Create a new index with the current user (you) as admin. Requires WRITER role on the server.
    """
    HTTPException_if_not_server_role(
        user, Roles.WRITER, message="Creating a new project requires WRITER permission on the server"
    )

    d = body.model_dump(exclude={"image_url"})
    d["image"] = create_image_from_url(body.image_url) if body.image_url else None

    try:
        create_project_index(
            ProjectSettings(**d),
            user.email,
        )
    except IndexAlreadyExists as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ApiError as e:
        raise HTTPException(
            status_code=400,
            detail=dict(info=f"Error on creating index: {e}", message=e.message, body=e.body),
        )

    if body.guest_role:
        set_project_guest_role(body.id, Roles[body.guest_role])


@app_index.put("/index/{ix}", status_code=status.HTTP_204_NO_CONTENT)
def modify_index(
    ix: Annotated[IndexId, Path(..., description="ID of the index to modify")],
    body: Annotated[UpdateIndexBody, Body(...)],
    user: User = Depends(authenticated_user),
):
    """
    Modify an existing index. Requires ADMIN role on the index.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.ADMIN)

    try:
        update_project_index(
            ProjectSettings(
                id=ix,
                **body.model_dump(exclude={"image_url"}),
                image=create_image_from_url(body.image_url) if body.image_url else None,
            )
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Index {ix} does not exist")

    if body.guest_role:
        set_project_guest_role(ix, Roles[body.guest_role])


@app_index.get("/index/{ix}")
def view_index(
    ix: IndexId = Path(..., description="ID of the index to view"), user: User = Depends(authenticated_user)
) -> IndexViewResponse:
    """
    Get details of a single index, including the user role. Requires at least LISTER role on the index.
    """
    try:
        d = get_project_settings(ix)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Index {ix} does not exist")
    except Exception:
        raise HTTPException(status_code=500, detail=f"Error reading index {ix} settings")

    HTTPException_if_not_project_index_role(user, ix, Roles.LISTER)
    role = get_user_project_role(user, project_index=ix, global_admin=False)

    bytes = index_size_in_bytes(ix)

    return IndexViewResponse(
        id=d.id,
        name=d.name or "",
        user_role=role.role if role else None,
        user_role_match=role.email if role else None,
        guest_role=get_project_guest_role(d.id),
        description=d.description or "",
        archived=d.archived or "",
        folder=d.folder or "",
        image_id=d.image.id if d.image else None,
        contact=d.contact or [],
        bytes=bytes,
    )


@app_index.post("/index/{ix}/archive", status_code=status.HTTP_204_NO_CONTENT)
def archive_index(
    ix: Annotated[IndexId, Path(..., description="ID of the index to (un)archive")],
    archived: Annotated[bool, Body(..., description="Boolean for setting archived to true or false")],
    user: User = Depends(authenticated_user),
):
    """
    Archive or unarchive the index. When an index is archived, it restricts usage, and adds a timestamp for when
    it was archived. Requires ADMIN role on the index.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.ADMIN)
    try:
        d = get_project_settings(ix)
        is_archived = d.archived is not None
        if is_archived == archived:
            return
        archived_date = str(datetime.now()) if archived else None
        update_project_index(ProjectSettings(id=ix, archived=archived_date))

    except IndexDoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} does not exist")


@app_index.delete("/index/{ix}", status_code=status.HTTP_204_NO_CONTENT)
def delete_index(ix: IndexId, user: User = Depends(authenticated_user)):
    """Delete the index. Requires ADMIN role on the index."""
    HTTPException_if_not_project_index_role(user, ix, Roles.ADMIN)
    try:
        delete_project_index(ix)
    except IndexDoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} does not exist")


@app_index.get("/index/{ix}/refresh", status_code=status.HTTP_204_NO_CONTENT)
def refresh(ix: str):
    """Refresh the elastic index. Use this if you need to make recently added documents searchable immediately."""
    refresh_index(ix)


@app_index.post("/index/{ix}/reindex")
def start_reindex(
    ix: IndexId,
    body: Annotated[ReindexBody, Body(...)],
    user: User = Depends(authenticated_user),
):
    HTTPException_if_not_project_index_role(user, ix, Roles.READER)
    HTTPException_if_not_project_index_role(user, body.destination, Roles.WRITER)
    filters = _standardize_filters(body.filters)

    queries = _standardize_queries(body.queries)
    return reindex(source_index=ix, destination_index=body.destination, queries=queries, filters=filters)


@app_index.get("/index/{ix}/image/{id}")
def get_index_image(ix: IndexId, id: str):
    """
    Get the image associated with the index. This endpoint doesn't require authentication,
    and only requires knowing the index ID and image ID.
    """

    try:
        image = get_project_image(ix)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Index {ix} does not exist")
    except Exception:
        raise HTTPException(status_code=500, detail=f"Error reading index {ix} settings")

    if image is None or image.id != id or image.base64 is None:
        raise HTTPException(status_code=404, detail=f"Image {id} does not exist for index {ix}")

    headers = {
        "X-Content-Type-Options": "nosniff",  ## security measure
        "Cache-Control": "public, max-age=31536000, immutable",  ## browser caching for unique URLs
    }

    content = base64.b64decode(image.base64)
    return Response(content=content, media_type="image/jpeg", headers=headers)
