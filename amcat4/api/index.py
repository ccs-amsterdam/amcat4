"""API Endpoints for document and index management."""

from datetime import datetime
from typing import Annotated, Mapping

from elastic_transport import ApiError
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Response, status
from pydantic import BaseModel, Field

from amcat4.projects.index import (
    IndexDoesNotExist,
    create_project_index,
    delete_project_index,
    list_user_project_indices,
    refresh_index,
    update_project_index,
)
from amcat4.api.auth import authenticated_user
from amcat4.api.index_query import _standardize_filters, _standardize_queries
from amcat4.models import (
    ContactInfo,
    FilterSpec,
    FilterValue,
    GuestRole,
    IndexId,
    ProjectSettings,
    Role,
    RoleEmailPattern,
    Roles,
    User,
)
from amcat4.projects.query import reindex
from amcat4.systemdata.roles import (
    get_project_guest_role,
    get_user_project_role,
    raise_if_not_project_index_role,
    raise_if_not_server_role,
    role_is_at_least,
    set_project_guest_role,
)
from amcat4.systemdata.settings import get_project_settings

app_index = APIRouter(prefix="", tags=["index"])

# TODO: rename to projects and add deprecated index route
# app_projects = APIRouter(prefix="/projects", tags=["projects"])
# app_index_deprecated = APIRouter(prefix="/projects", tags=["projects"], deprecated=True)
#
# add both decorators to all functions, and register both routers

# TODO: Decide on best way to validate and document fields.
# - Notice the different style for NameField, description and the rest
#   The description one feels best, because it only postpones deciding optional or not.
#   But this changes how OpenAPI documents it (maybe for the better?)
# - Ideally we don't repeat the description, but maybe we should repeat the type tp make it explicit in the models
# (Relevant to do well, because this is also how we can set up an MCP server later)

# FIELD ANNOTATIONS
IdField = Annotated[IndexId, Field(description="ID of the index")]
NameField = Field(description="Name of the index")
DescriptionField = Annotated[str, Field(description="Description of the index")]
GuestRoleField = Annotated[GuestRole | None, Field(description="Guest role for the index")]
FolderField = Annotated[str | None, Field(description="Folder for the index")]
ImageUrlField = Annotated[str | None, Field(description="Image URL for the index")]
ContactField = Annotated[list[ContactInfo] | None, Field(description="Contact info for the index")]

UserRoleField = Annotated[Role | None, Field(description="Role of the current user on this index")]
UserRoleMatchField = Annotated[RoleEmailPattern | None, Field(description="Email pattern that determined the user role")]
ArchivedField = Annotated[str | None, Field(description="Timestamp of when the index was archived, or null if not archived")]


# REQUEST MODELS
class UpdateIndexBody(BaseModel):
    """Form to update an existing index."""

    name: Annotated[str | None, NameField] = None
    description: DescriptionField | None = None
    guest_role: GuestRoleField = None
    folder: FolderField = None
    image_url: ImageUrlField = None
    contact: ContactField = None


# the create body extends the update body with an id field
class CreateIndexBody(UpdateIndexBody):
    """Form to create a new index."""

    id: IdField


# RESPONSE MODELS
class IndexListResponse(BaseModel):
    id: IdField
    name: Annotated[str | None, NameField]
    description: DescriptionField | None
    user_role: UserRoleField
    user_role_match: UserRoleMatchField
    archived: ArchivedField
    folder: FolderField
    image_url: ImageUrlField


# the list response plus guest role and contact info
class IndexViewResponse(IndexListResponse):
    guest_role: GuestRoleField
    contact: ContactField


@app_index.get("/index/")
def index_list(current_user: User = Depends(authenticated_user)) -> list[IndexListResponse]:
    """
    List indices from this server that the user has access to.

    Returns a list of dicts with index details, including the user role.
    """

    ix_list: list = []
    for ix, role in list_user_project_indices(current_user):
        ix_list.append(
            dict(
                id=ix.id,
                name=ix.name,
                user_role=role.role if role else None,
                user_role_match=role.email if role else None,
                description=ix.description or "",
                archived=ix.archived or "",
                folder=ix.folder or "",
                image_url=ix.image_url,
            )
        )

    return ix_list


@app_index.post("/index/", status_code=status.HTTP_201_CREATED)
def create_index(
    body: Annotated[CreateIndexBody, Body()],
    user: User = Depends(authenticated_user),
):
    """
    Create a new index, setting the current user to admin (owner).

    POST data should be json containing name and optional guest_role
    """
    raise_if_not_server_role(user, Roles.WRITER, message="Creating a new project requires WRITER permission on the server")

    try:
        create_project_index(
            ProjectSettings(
                id=body.id,
                name=body.name,
                description=body.description,
                folder=body.folder,
                image_url=body.image_url,
                contact=body.contact,
            ),
            user.email,
        )
    except ApiError as e:
        raise HTTPException(
            status_code=400,
            detail=dict(info=f"Error on creating index: {e}", message=e.message, body=e.body),
        )

    if body.guest_role:
        set_project_guest_role(body.id, Roles[body.guest_role])


@app_index.put("/index/{ix}")
def modify_index(
    ix: Annotated[IndexId, Path(..., description="ID of the index to modify")],
    body: Annotated[UpdateIndexBody, Body()],
    user: User = Depends(authenticated_user),
):
    """
    Modify the index.

    POST data should be json containing the changed values (i.e. name, description, guest_role)

    User needs admin rights on the index
    """
    raise_if_not_project_index_role(user, ix, Roles.ADMIN)

    update_project_index(
        ProjectSettings(
            id=ix,
            name=body.name,
            description=body.description,
            folder=body.folder,
            image_url=body.image_url,
            contact=body.contact,
        )
    )

    if body.guest_role:
        set_project_guest_role(ix, Roles[body.guest_role])


@app_index.get("/index/{ix}")
def view_index(
    ix: IndexId = Path(..., description="ID of the index to view"), user: User = Depends(authenticated_user)
) -> IndexViewResponse:
    """
    View the index.
    """
    try:
        d = get_project_settings(ix)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Index {ix} does not exist")

    role = get_user_project_role(user, project_index=ix)
    if not role_is_at_least(role, Roles.LISTER):
        raise HTTPException(403, "Viewing a project requires LISTER permission on the project")

    return IndexViewResponse(
        id=d.id,
        name=d.name or "",
        user_role=role.role if role else None,
        user_role_match=role.email if role else None,
        guest_role=get_project_guest_role(d.id),
        description=d.description or "",
        archived=d.archived or "",
        folder=d.folder or "",
        image_url=d.image_url or "",
        contact=d.contact or [],
    )


@app_index.post("/index/{ix}/archive", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def archive_index(
    ix: Annotated[IndexId, Path(..., description="ID of the index to (un)archive")],
    archived: Annotated[bool, Body(..., description="Boolean for setting archived to true or false")],
    user: User = Depends(authenticated_user),
):
    """
    Archive or unarchive the index. When an index is archived, it restricts usage, and adds a timestamp for when
    it was archived.
    """
    raise_if_not_project_index_role(user, ix, Roles.ADMIN)
    try:
        d = get_project_settings(ix)
        is_archived = d.archived is not None
        if is_archived == archived:
            return
        archived_date = str(datetime.now()) if archived else None
        update_project_index(ProjectSettings(id=ix, archived=archived_date))

    except IndexDoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} does not exist")


@app_index.delete("/index/{ix}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_index(ix: IndexId, user: User = Depends(authenticated_user)):
    """Delete the index."""
    raise_if_not_project_index_role(user, ix, Roles.ADMIN)
    try:
        delete_project_index(ix)
    except IndexDoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} does not exist")


@app_index.get("/index/{ix}/refresh", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def refresh(ix: str):
    refresh_index(ix)


@app_index.post("/index/{ix}/reindex")
def start_reindex(
    ix: IndexId,
    destination: str = Body(..., description="Email address of the user to add"),
    queries: Annotated[
        str | list[str] | dict[str, str] | None,
        Body(
            description=(
                "Query/Queries to select documents to reindex. Value should be a single query string, "
                "a list of query strings, or a dict of {'label': 'query'}"
            ),
        ),
    ] = None,
    filters: Annotated[
        Mapping[str, FilterValue | list[FilterValue] | FilterSpec] | None,
        Body(
            description=(
                "Field filters, should be a dict of field names to filter specifications, "
                "which can be either a value, a list of values, or a FilterSpec dict"
            ),
        ),
    ] = None,
    user: User = Depends(authenticated_user),
):
    raise_if_not_project_index_role(user, ix, Roles.READER)
    raise_if_not_project_index_role(user, destination, Roles.WRITER)
    filters = _standardize_filters(filters)
    queries = _standardize_queries(queries)
    return reindex(source_index=ix, destination_index=destination, queries=queries, filters=filters)
