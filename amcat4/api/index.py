"""API Endpoints for document and index management."""

import logging
from datetime import datetime
from http import HTTPStatus
from typing import Annotated, Any, Literal, Mapping

import elasticsearch
from elastic_transport import ApiError
from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from pydantic import BaseModel

from amcat4 import fields as index_fields
from amcat4 import index
from amcat4.api.auth import authenticated_user, authenticated_writer, check_fields_access, check_role
from amcat4.fields import field_stats, field_values
from amcat4.index import get_index_user_role, refresh_system_index, remove_role, set_role
from amcat4.models import ContactInfo, CreateField, FieldSpec, FieldType, FilterSpec, FilterValue, UpdateField
from amcat4.query import reindex

from .query import _standardize_filters, _standardize_queries

app_index = APIRouter(prefix="/index", tags=["index"])

RoleType = Literal["ADMIN", "WRITER", "READER", "METAREADER"]
GuestRoleType = Literal["WRITER", "READER", "METAREADER"]


@app_index.get("/")
def index_list(current_user: str = Depends(authenticated_user)):
    """
    List indices from this server that the user has access to.

    Returns a list of dicts with index details, including the user role.
    """

    def index_to_dict(ix: index.Index, role: index.Role) -> dict:
        ix_dict = ix._asdict()

        ix_dict = dict(
            id=ix_dict["id"],
            name=ix_dict["name"],
            user_role=role.name,
            description=ix_dict.get("description", ""),
            archived=ix_dict.get("archived", ""),
            folder=ix_dict.get("folder", ""),
            image_url=ix_dict.get("image_url", ""),
        )
        return ix_dict

    return [index_to_dict(ix, role) for ix, role in index.list_user_indices(current_user)]


class NewIndex(BaseModel):
    """Form to create a new index."""

    id: str
    name: str | None = None
    guest_role: GuestRoleType | None = None
    description: str | None = None
    folder: str | None = None
    image_url: str | None = None
    contact: list[ContactInfo] | None = None


@app_index.post("/", status_code=status.HTTP_201_CREATED)
def create_index(new_index: NewIndex, current_user: str = Depends(authenticated_writer)):
    """
    Create a new index, setting the current user to admin (owner).

    POST data should be json containing name and optional guest_role
    """
    guest_role = new_index.guest_role and index.GuestRole[new_index.guest_role.upper()]

    try:
        index.create_index(
            new_index.id,
            guest_role=guest_role,
            name=new_index.name,
            description=new_index.description,
            admin=current_user if current_user != "_admin" else None,
            folder=new_index.folder,
            image_url=new_index.image_url,
            contact=new_index.contact,
        )

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
    guest_role: GuestRoleType | Literal["NONE"] | None = None
    archive: bool | None = None
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
    check_role(user, index.Role.ADMIN, ix)
    guest_role = index.GuestRole[data.guest_role] if data.guest_role is not None else None
    archived = None
    if data.archive is not None:
        d = index.get_index(ix)
        is_archived = d.archived is not None and d.archived != ""
        if is_archived != data.archive:
            archived = str(datetime.now()) if data.archive else ""

    index.modify_index(
        ix,
        name=data.name,
        description=data.description,
        guest_role=guest_role,
        archived=archived,
        folder=data.folder,
        image_url=data.image_url,
        contact=data.contact,
        # unarchive=unarchive,
    )
    refresh_system_index()


@app_index.get("/{ix}")
def view_index(ix: str, user: str = Depends(authenticated_user)):
    """
    View the index.
    """
    try:
        check_role(user, index.Role.METAREADER, ix)
        d = index.get_index(ix)._asdict()

        try:
            guest_role = index.GuestRole(d["guest_role"])
        except ValueError:
            logging.warning(f"Invalid guest role {d['guest_role']} for index {ix}")
            guest_role = index.GuestRole(0)

        user_role = get_index_user_role(guest_role, d["roles"], user)

        d.pop("roles", None)
        d["user_role"] = user_role.name
        d["guest_role"] = guest_role.name
        d["description"] = d.get("description", "") or ""
        d["name"] = d.get("name", "") or ""
        d["folder"] = d.get("folder", "") or ""
        d["image_url"] = d.get("image_url")
        return d

    except index.IndexDoesNotExist:
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
    check_role(user, index.Role.ADMIN, ix)
    try:
        d = index.get_index(ix)
        is_archived = d.archived is not None
        if is_archived == archived:
            return
        archived_date = str(datetime.now()) if archived else None
        index.modify_index(ix, archived=archived_date)

    except index.IndexDoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} does not exist")


@app_index.delete("/{ix}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_index(ix: str, user: str = Depends(authenticated_user)):
    """Delete the index."""
    check_role(user, index.Role.ADMIN, ix)
    try:
        index.delete_index(ix)
    except index.IndexDoesNotExist:
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
    check_role(user, index.Role.WRITER, ix)
    return index.upload_documents(ix, documents, fields, operation)


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
    check_role(user, index.Role.READER, ix)
    kargs = {}
    if fields:
        kargs["_source"] = fields
    try:
        return index.get_document(ix, docid, **kargs)
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
    check_role(user, index.Role.WRITER, ix)
    try:
        index.update_document(ix, docid, update)
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
    check_role(user, index.Role.WRITER, ix)
    try:
        index.delete_document(ix, docid)
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
    check_role(user, index.Role.WRITER, ix)
    index_fields.create_fields(ix, fields)
    return "", HTTPStatus.NO_CONTENT


@app_index.get("/{ix}/fields")
def get_fields(ix: str, user: str = Depends(authenticated_user)):
    """
    Get the fields (columns) used in this index.

    Returns a json array of {name, type} objects
    """
    check_role(user, index.Role.METAREADER, ix)
    return index.get_fields(ix)


@app_index.put("/{ix}/fields")
def update_fields(
    ix: str, fields: Annotated[dict[str, UpdateField], Body(description="")], user: str = Depends(authenticated_user)
):
    """
    Update the field settings
    """
    check_role(user, index.Role.WRITER, ix)

    index_fields.update_fields(ix, fields)
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
    check_role(user, index.Role.READER, ix)
    values = field_values(ix, field, size=2001)
    if len(values) > 2000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Field {field} has more than 2000 unique values",
        )
    return values


@app_index.get("/{ix}/fields/{field}/stats")
def get_field_stats(ix: str, field: str, user: str = Depends(authenticated_user)):
    """Get statistics for a specific value. Only works for numeric (incl date) fields."""
    check_fields_access(ix, user, [FieldSpec(name=field)])
    return field_stats(ix, field)


@app_index.get("/{ix}/users")
def list_index_users(ix: str, user: str = Depends(authenticated_user)):
    """
    List the users in this index.

    Allowed for global admin and local readers
    """
    if index.get_global_role(user) != index.Role.ADMIN:
        check_role(user, index.Role.READER, ix)
    return [{"email": u, "role": r.name} for (u, r) in index.list_users(ix).items()]


@app_index.post("/{ix}/users", status_code=status.HTTP_201_CREATED)
def add_index_users(
    ix: str,
    email: str = Body(..., description="Email address of the user to add"),
    role: RoleType = Body(..., description="Role of the user to add"),
    user: str = Depends(authenticated_user),
):
    """
    Add an existing user to this index.

    This requires ADMIN rights on the index or server
    """
    r = index.Role[role]
    check_role(user, index.Role.ADMIN, ix)
    set_role(ix, email, r)
    return {"user": email, "index": ix, "role": r.name}


@app_index.put("/{ix}/users/{email}")
def modify_index_user(
    ix: str,
    email: str,
    role: RoleType = Body(..., description="New role for the user", embed=True),
    user: str = Depends(authenticated_user),
):
    """
    Change the role of an existing user.

    This requires ADMIN rights on the index or server
    """
    r = index.Role[role]
    check_role(user, index.Role.ADMIN, ix)
    set_role(ix, email, r)
    return {"user": email, "index": ix, "role": r.name}


@app_index.delete("/{ix}/users/{email}")
def remove_index_user(ix: str, email: str, user: str = Depends(authenticated_user)):
    """
    Remove this user from the index.

    This requires ADMIN rights on the index or server
    """
    check_role(user, index.Role.ADMIN, ix)
    remove_role(ix, email)
    return {"user": email, "index": ix, "role": None}


@app_index.get("/{ix}/refresh", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def refresh_index(ix: str):
    index.refresh_index(ix)


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
    check_role(user, index.Role.READER, ix)
    check_role(user, index.Role.WRITER, destination)
    filters = _standardize_filters(filters)
    queries = _standardize_queries(queries)
    return reindex(source_index=ix, destination_index=destination, queries=queries, filters=filters)
