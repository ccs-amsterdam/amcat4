"""API Endpoints for document and index management."""

from datetime import datetime
from http import HTTPStatus
from typing import Annotated, Any, Literal, Mapping

import elasticsearch
from elastic_transport import ApiError
from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from pydantic import BaseModel

from amcat4 import projectdata as _projects
from amcat4.api.auth import authenticated_user, authenticated_writer
from amcat4.api.query import _standardize_filters, _standardize_queries
from amcat4.models import (
    ContactInfo,
    CreateField,
    FieldSpec,
    FieldType,
    FilterSpec,
    FilterValue,
    GuestRole,
    IndexSettings,
    Role,
    UpdateField,
)
from amcat4.query import reindex
from amcat4.systemdata import fields as _fields
from amcat4.systemdata.roles import elastic_create_or_update_role, elastic_delete_role, elastic_get_role, raise_if_not_has_role
from amcat4.systemdata.settings import elastic_get_index_settings

app_index = APIRouter(prefix="/index", tags=["index"])


@app_index.get("/")
def index_list(current_user: str = Depends(authenticated_user)):
    """
    List indices from this server that the user has access to.

    Returns a list of dicts with index details, including the user role.
    """

    def index_to_dict(ix: IndexSettings, role: Role) -> dict:
        return dict(
            id=ix.id,
            name=ix.name,
            user_role=role,
            description=ix.description or "",
            archived=ix.archived or "",
            folder=ix.folder or "",
            image_url=ix.image_url,
        )

    return [index_to_dict(ix, role) for ix, role in _projects.list_user_project_indices(current_user)]


@app_index.post("/", status_code=status.HTTP_201_CREATED)
def create_index(new_index: IndexSettings, current_user: str = Depends(authenticated_writer)):
    """
    Create a new index, setting the current user to admin (owner).

    POST data should be json containing name and optional guest_role
    """
    try:
        _projects.create_project_index(new_index, current_user)
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
    guest_role: GuestRole | Literal["NONE"] | None = None
    folder: str | None = None
    image_url: str | None = None
    contact: list[ContactInfo] | None = None


@app_index.put("/{ix}")
def modify_index(ix: str, data: ChangeIndex, user: str = Depends(authenticated_user)):
    """
    Modify the index.

    POST data should be json containing the changed values (i.e. name, description, guest_role)

    User needs admin rights on the index
    """
    _projects.raise_if_not_project_exists(ix)
    raise_if_not_has_role(user, ix, "ADMIN")

    _projects.update_project_index(
        IndexSettings(
            id=ix,
            name=data.name,
            description=data.description,
            guest_role=data.guest_role,
            folder=data.folder,
            image_url=data.image_url,
            contact=data.contact,
        )
    )


@app_index.get("/{ix}")
def view_index(ix: str, user: str = Depends(authenticated_user)):
    """
    View the index.
    """
    try:
        raise_if_not_has_role(user, ix, "LISTER")
        d = elastic_get_index_settings(ix)
        role = elastic_get_role(user, ix)

        return dict(
            id=d.id,
            name=d.name or "",
            user_role=role,
            guest_role=d.guest_role,
            description=d.description or "",
            archived=d.archived or "",
            folder=d.folder or "",
            image_url=d.image_url or "",
            contact=d.contact or [],
        )

    except _projects.IndexDoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} does not exist")


@app_index.post("/{ix}/archive", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def archive_index(
    ix: str,
    archived: Annotated[bool, Body(description="Boolean for setting archived to true or false")],
    user: str = Depends(authenticated_user),
):
    """
    Archive or unarchive the index. When an index is archived, it restricts usage, and adds a timestamp for when
    it was archived.
    """
    raise_if_not_has_role(user, ix, "ADMIN")
    try:
        d = elastic_get_index_settings(ix)
        is_archived = d.archived is not None
        if is_archived == archived:
            return
        archived_date = str(datetime.now()) if archived else None
        _projects.update_project_index(IndexSettings(id=ix, archived=archived_date))

    except _projects.IndexDoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} does not exist")


@app_index.delete("/{ix}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_index(ix: str, user: str = Depends(authenticated_user)):
    """Delete the index."""
    raise_if_not_has_role(user, ix, "ADMIN")
    try:
        _projects.delete_project_index(ix)
    except _projects.IndexDoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} does not exist")


@app_index.post("/{ix}/documents", status_code=status.HTTP_201_CREATED)
def upload_documents(
    ix: str,
    documents: Annotated[list[dict[str, Any]], Body(description="The documents to upload")],
    fields: Annotated[
        dict[str, FieldType | CreateField] | None,
        Body(
            description="If a field in documents does not yet exist, you can create it on the spot. "
            "If you only need to specify the type, and use the default settings, "
            "you can use the short form: {field: type}"
        ),
    ] = None,
    operation: Annotated[
        Literal["index", "update", "create"],
        Body(
            description="The operation to perform. Default is index, which replaces documents that already exist. "
            "The 'update' operation behaves as an upsert (create or update). If an identical document (or document with "
            "identical identifiers) already exists, the uploaded fields will be created or overwritten. If there are fields "
            "in the original document that are not in the uploaded document, they will NOT be removed. "
            "The 'create' operation only uploads new documents, and returns failures for documents with existing ids"
        ),
    ] = "index",
    user: str = Depends(authenticated_user),
):
    """
    Upload documents to this server. Returns a list of ids for the uploaded documents
    """
    raise_if_not_has_role(user, ix, "WRITER")
    return _projects.upload_documents(ix, documents, fields, operation)


@app_index.get("/{ix}/documents/{docid}")
def get_document(
    ix: str,
    docid: str,
    fields: str | None = None,
    user: str = Depends(authenticated_user),
):
    """
    Get a single document by id.

    GET request parameters:
    fields - Comma separated list of fields to return (default: all fields)
    """
    raise_if_not_has_role(user, ix, "READER")
    kargs = {}
    if fields:
        kargs["_source"] = fields
    try:
        return _projects.get_document(ix, docid, **kargs)
    except elasticsearch.exceptions.NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {ix}/{docid} not found",
        )


@app_index.put(
    "/{ix}/documents/{docid}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def update_document(
    ix: str,
    docid: str,
    update: dict = Body(...),
    user: str = Depends(authenticated_user),
):
    """
    Update a document.

    PUT request body should be a json {field: value} mapping of fields to update
    """
    raise_if_not_has_role(user, ix, "WRITER")
    try:
        _projects.update_document(ix, docid, update)
    except elasticsearch.exceptions.NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {ix}/{docid} not found",
        )


@app_index.delete(
    "/{ix}/documents/{docid}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_document(ix: str, docid: str, user: str = Depends(authenticated_user)):
    """Delete this document."""
    raise_if_not_has_role(user, ix, "WRITER")
    try:
        _projects.delete_document(ix, docid)
    except elasticsearch.exceptions.NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {ix}/{docid} not found",
        )


@app_index.post("/{ix}/fields")
def create_fields(
    ix: str,
    fields: Annotated[
        dict[str, FieldType | CreateField],
        Body(
            description="Either a dictionary that maps field names to field specifications"
            "({field: {type: 'text', identifier: True }}), "
            "or a simplified version that only specifies the type ({field: type})"
        ),
    ],
    user: str = Depends(authenticated_user),
):
    """
    Create fields
    """
    raise_if_not_has_role(user, ix, "WRITER")

    _fields.create_fields(ix, fields)
    return "", HTTPStatus.NO_CONTENT


@app_index.get("/{ix}/fields")
def get_fields(ix: str, user: str = Depends(authenticated_user)):
    """
    Get the fields (columns) used in this index.

    Returns a json array of {name, type} objects
    """
    raise_if_not_has_role(user, ix, "METAREADER")
    return _fields.get_fields(ix)


@app_index.put("/{ix}/fields")
def update_fields(
    ix: str, fields: Annotated[dict[str, UpdateField], Body(description="")], user: str = Depends(authenticated_user)
):
    """
    Update the field settings
    """
    raise_if_not_has_role(user, ix, "WRITER")

    _fields.update_fields(ix, fields)
    return "", HTTPStatus.NO_CONTENT


@app_index.get("/{ix}/fields/{field}/values")
def get_field_values(ix: str, field: str, user: str = Depends(authenticated_user)):
    """
    Get unique values for a specific field. Should mainly/only be used for tag fields.
    Main purpose is to provide a list of values for a dropdown menu.

    TODO: at the moment 'only' returns top 2000 values. Currently throws an
    error if there are more than 2000 unique values. We can increase this limit, but
    there should be a limit. Querying could be an option, but not sure if that is
    efficient, since elastic has to aggregate all values first.
    """
    raise_if_not_has_role(user, ix, "READER")
    values = _fields.field_values(ix, field, size=2001)
    if len(values) > 2000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Field {field} has more than 2000 unique values",
        )
    return values


@app_index.get("/{ix}/fields/{field}/stats")
def get_field_stats(ix: str, field: str, user: str = Depends(authenticated_user)):
    """Get statistics for a specific value. Only works for numeric (incl date) fields."""
    _fields.check_fields_access(ix, user, [FieldSpec(name=field)])
    return _fields.field_stats(ix, field)


@app_index.get("/{ix}/users")
def list_index_users(ix: str, user: str = Depends(authenticated_user)):
    """
    List the users in this index.

    Allowed for global admin and local readers
    """
    raise_if_not_has_role(user, ix, "READER")
    return [{"email": u, "role": r.name} for (u, r) in index.list_users(ix).items()]


@app_index.post("/{ix}/users", status_code=status.HTTP_201_CREATED)
def add_index_users(
    ix: str,
    email: str = Body(..., description="Email address of the user to add"),
    role: Role = Body(..., description="Role of the user to add"),
    user: str = Depends(authenticated_user),
):
    """
    Add an existing user to this index.

    This requires ADMIN rights on the index or server
    """
    raise_if_not_has_role(user, ix, "ADMIN")
    elastic_create_or_update_role(email, ix, role)
    return {"user": email, "index": ix, "role": role}


@app_index.put("/{ix}/users/{email}")
def modify_index_user(
    ix: str,
    email: str,
    role: Role = Body(..., description="New role for the user", embed=True),
    user: str = Depends(authenticated_user),
):
    """
    Change the role of an existing user.

    This requires ADMIN rights on the index or server
    """
    raise_if_not_has_role(user, ix, "ADMIN")
    elastic_create_or_update_role(email, ix, role)
    return {"user": email, "index": ix, "role": r}


@app_index.delete("/{ix}/users/{email}")
def remove_index_user(ix: str, email: str, user: str = Depends(authenticated_user)):
    """
    Remove this user from the index.

    This requires ADMIN rights on the index or server
    """
    raise_if_not_has_role(user, ix, "ADMIN")
    elastic_delete_role(email, ix)
    return {"user": email, "index": ix, "role": None}


@app_index.get("/{ix}/refresh", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def refresh_index(ix: str):
    _projects.refresh_index(ix)


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
    user: str = Depends(authenticated_user),
):
    raise_if_not_has_role(user, ix, "READER")
    raise_if_not_has_role(user, destination, "WRITER")
    filters = _standardize_filters(filters)
    queries = _standardize_queries(queries)
    return reindex(source_index=ix, destination_index=destination, queries=queries, filters=filters)
