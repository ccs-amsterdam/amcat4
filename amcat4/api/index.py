"""API Endpoints for document and index management."""

from datetime import datetime
from typing import Annotated, Literal, Mapping

from elastic_transport import ApiError
from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from pydantic import BaseModel

from amcat4.project_index import (
    IndexDoesNotExist,
    create_project_index,
    delete_project_index,
    list_user_project_indices,
    raise_if_not_project_exists,
    refresh_index,
    update_project_index,
)
from amcat4.api.auth import authenticated_user
from amcat4.api.query import _standardize_filters, _standardize_queries
from amcat4.models import (
    ContactInfo,
    FilterSpec,
    FilterValue,
    IndexSettings,
    Role,
    User,
)
from amcat4.query import reindex
from amcat4.systemdata.roles import (
    get_guest_role,
    get_project_index_role,
    raise_if_not_project_index_role,
    raise_if_not_server_role,
    set_guest_role,
)
from amcat4.systemdata.settings import elastic_get_index_settings

app_index = APIRouter(prefix="/index", tags=["index"])


@app_index.get("/")
def index_list(current_user: User = Depends(authenticated_user)):
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
                user_role_match=role.email_pattern if role else None,
                description=ix.description or "",
                archived=ix.archived or "",
                folder=ix.folder or "",
                image_url=ix.image_url,
            )
        )

    return ix_list


@app_index.post("/", status_code=status.HTTP_201_CREATED)
def create_index(new_index: IndexSettings, user: User = Depends(authenticated_user)):
    """
    Create a new index, setting the current user to admin (owner).

    POST data should be json containing name and optional guest_role
    """
    raise_if_not_server_role(user, Role.WRITER)
    try:
        create_project_index(new_index, user.email)
    except ApiError as e:
        raise HTTPException(
            status_code=400,
            detail=dict(info=f"Error on creating index: {e}", message=e.message, body=e.body),
        )


# TODO Yes, this should be linked to the actual roles enum
class ChangeIndex(BaseModel):
    """Form to update an existing index."""

    name: str | None = None
    description: str | None = None
    guest_role: Literal["NONE", "READER", "WRITER"] | None = None
    folder: str | None = None
    image_url: str | None = None
    contact: list[ContactInfo] | None = None


@app_index.put("/{ix}")
def modify_index(ix: str, data: ChangeIndex, user: User = Depends(authenticated_user)):
    """
    Modify the index.

    POST data should be json containing the changed values (i.e. name, description, guest_role)

    User needs admin rights on the index
    """
    raise_if_not_project_exists(ix)
    raise_if_not_project_index_role(user, ix, Role.ADMIN)

    update_project_index(
        IndexSettings(
            id=ix,
            name=data.name,
            description=data.description,
            folder=data.folder,
            image_url=data.image_url,
            contact=data.contact,
        )
    )

    if data.guest_role:
        set_guest_role(ix, Role(data.guest_role))


@app_index.get("/{ix}")
def view_index(ix: str, user: User = Depends(authenticated_user)):
    """
    View the index.
    """
    try:
        raise_if_not_project_index_role(user, ix, Role.LISTER)
        d = elastic_get_index_settings(ix)
        role = get_project_index_role(email=user.email, project_index=ix)

        return dict(
            id=d.id,
            name=d.name or "",
            user_role=role.role if role else None,
            user_role_match=role.email_pattern if role else None,
            guest_role=get_guest_role(d.id),
            description=d.description or "",
            archived=d.archived or "",
            folder=d.folder or "",
            image_url=d.image_url or "",
            contact=d.contact or [],
        )

    except IndexDoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} does not exist")


@app_index.post("/{ix}/archive", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def archive_index(
    ix: str,
    archived: Annotated[bool, Body(description="Boolean for setting archived to true or false")],
    user: User = Depends(authenticated_user),
):
    """
    Archive or unarchive the index. When an index is archived, it restricts usage, and adds a timestamp for when
    it was archived.
    """
    raise_if_not_project_index_role(user, ix, Role.ADMIN)
    try:
        d = elastic_get_index_settings(ix)
        is_archived = d.archived is not None
        if is_archived == archived:
            return
        archived_date = str(datetime.now()) if archived else None
        update_project_index(IndexSettings(id=ix, archived=archived_date))

    except IndexDoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} does not exist")


@app_index.delete("/{ix}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_index(ix: str, user: User = Depends(authenticated_user)):
    """Delete the index."""
    raise_if_not_project_index_role(user, ix, Role.ADMIN)
    try:
        delete_project_index(ix)
    except IndexDoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} does not exist")


@app_index.get("/{ix}/refresh", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def refresh(ix: str):
    refresh_index(ix)


@app_index.post("/{ix}/reindex")
def start_reindex(
    ix: str,
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
    raise_if_not_project_index_role(user, ix, Role.READER)
    raise_if_not_project_index_role(user, destination, Role.WRITER)
    filters = _standardize_filters(filters)
    queries = _standardize_queries(queries)
    return reindex(source_index=ix, destination_index=destination, queries=queries, filters=filters)
