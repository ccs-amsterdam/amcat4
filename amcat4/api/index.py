"""API Endpoints for document and index management."""
from http import HTTPStatus
from typing import Literal, Optional, Mapping, List

import elasticsearch
from fastapi import APIRouter, HTTPException, status, Response
from fastapi.params import Depends, Body
from pydantic import BaseModel
from pydantic.config import Extra

from amcat4 import elastic, index
from amcat4.api.auth import authenticated_user, authenticated_writer, check_role
from amcat4.api.common import py2dict
from amcat4.index import Role, refresh, set_role, get_role, get_guest_role, list_known_indices, set_guest_role, \
    get_global_role, list_users, remove_role, IndexDoesNotExist

app_index = APIRouter(
    prefix="/index",
    tags=["index"])

RoleType = Literal["ADMIN", "WRITER", "READER", "METAREADER", "admin", "writer", "reader", "metareader"]


@app_index.get("/")
def index_list(current_user: str = Depends(authenticated_user)):
    """
    List index from this server.

    Returns a list of dicts containing name, role, and guest attributes
    """
    return [{"name": ix} for ix in list_known_indices(current_user)]


class NewIndex(BaseModel):
    """Form to create a new index."""

    name: str
    guest_role: Optional[RoleType]


@app_index.post("/", status_code=status.HTTP_201_CREATED)
def create_index(new_index: NewIndex, current_user: str = Depends(authenticated_writer)):
    """
    Create a new index, setting the current user to admin (owner).

    POST data should be json containing name and optional guest_role
    """
    guest_role = Role[new_index.guest_role.upper()] if new_index.guest_role else Role.NONE
    index.create_index(new_index.name, guest_role=guest_role)
    set_role(new_index.name, current_user, Role.ADMIN)


# TODO Yes, this should be linked to the actual roles enum
class ChangeIndex(BaseModel):
    """Form to update an existing index."""

    guest_role: Literal["ADMIN", "WRITER", "READER", "METAREADER", "NONE",
                        "admin", "writer", "reader", "metareader", "none"]


@app_index.put("/{ix}")
def modify_index(ix: str, data: ChangeIndex, user: str = Depends(authenticated_user)):
    """
    Modify the index.

    Currently only supports modifying guest_role
    POST data should be json containing the changed values (i.e. guest_role)

    User needs admin rights on the index
    """
    check_role(user, Role.ADMIN, ix)
    guest_role = Role[data.guest_role.upper()]
    set_guest_role(ix, guest_role)


@app_index.get("/{ix}")
def view_index(ix: str, user: str = Depends(authenticated_user)):
    """
    View the index.
    """
    check_role(user, Role.METAREADER, ix, required_global_role=Role.WRITER)
    try:
        guest_role = get_guest_role(ix)
    except IndexDoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} does not exist")

    return {"index": ix, "guest_role": "NONE" if guest_role is None else guest_role.name}


@app_index.delete("/{ix}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_index(ix: str, user: str = Depends(authenticated_user)):
    """Delete the index."""
    check_role(user, Role.ADMIN, ix)
    index.delete_index(ix)


class Document(BaseModel):
    """Form to create (upload) a new document."""

    title: str
    date: str
    text: str
    url: Optional[str]

    class Config:
        """Allow any extra fields."""

        extra = Extra.allow


@app_index.post("/{ix}/documents", status_code=status.HTTP_201_CREATED)
def upload_documents(
        ix: str,
        documents: List[Document] = Body(None, description="The documents to upload"),
        columns: Optional[Mapping[str, str]] = Body(None, description="Optional Specification of field (column) types"),
        user: str = Depends(authenticated_user)):
    """
    Upload documents to this server.

    JSON payload should contain a `documents` key, and may contain a `columns` key:
    {
      "documents": [{"title": .., "date": .., "text": .., ...}, ...],
      "columns": {<field>: <type>, ...}
    }
    Returns a list of ids for the uploaded documents
    """
    check_role(user, Role.WRITER, ix)
    documents = [py2dict(doc) for doc in documents]
    return elastic.upload_documents(ix, documents, columns)


@app_index.get("/{ix}/documents/{docid}")
def get_document(ix: str, docid: str, fields: Optional[str] = None, user: str = Depends(authenticated_user)):
    """
    Get a single document by id.

    GET request parameters:
    fields - Comma separated list of fields to return (default: all fields)
    """
    check_role(user, Role.READER, ix)
    kargs = {}
    if fields:
        kargs['_source'] = fields
    try:
        return elastic.get_document(ix, docid, **kargs)
    except elasticsearch.exceptions.NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {ix}/{docid} not found")


@app_index.put("/{ix}/documents/{docid}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def update_document(ix: str, docid: str, update: dict = Body(...), user: str = Depends(authenticated_user)):
    """
    Update a document.

    PUT request body should be a json {field: value} mapping of fields to update
    """
    check_role(user, Role.WRITER, ix)
    try:
        elastic.update_document(ix, docid, update)
    except elasticsearch.exceptions.NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {ix}/{docid} not found")


@app_index.delete("/{ix}/documents/{docid}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_document(ix: str, docid: str, user: str = Depends(authenticated_user)):
    """Delete this document."""
    check_role(user, Role.WRITER, ix)
    try:
        elastic.delete_document(ix, docid)
    except elasticsearch.exceptions.NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {ix}/{docid} not found")


@app_index.get("/{ix}/fields")
def get_fields(ix: str, _=Depends(authenticated_user)):
    """
    Get the fields (columns) used in this index.

    Returns a json array of {name, type} objects
    """
    indices = ix.split(',')
    return elastic.get_fields(indices)


@app_index.post("/{ix}/fields")
def set_fields(ix: str, body: dict = Body(...), user: str = Depends(authenticated_user)):
    """
    Set the field types used in this index.

    POST body should be a dict of {field: type} or {field: {type: type, meta: meta}}
    """
    check_role(user, Role.WRITER, ix)
    elastic.set_fields(ix, body)
    return "", HTTPStatus.NO_CONTENT


@app_index.get("/{ix}/fields/{field}/values")
def get_values(ix: str, field: str, _=Depends(authenticated_user)):
    """Get the fields (columns) used in this index."""
    return elastic.get_values(ix, field)


@app_index.get("/{ix}/users")
def list_index_users(ix: str, user: str = Depends(authenticated_user)):
    """
    List the users in this index.

    Allowed for global admin and local readers
    """
    if get_global_role(user) != Role.ADMIN:
        check_role(user, Role.READER, ix)
    return [{"email": u, "role": r.name} for (u, r) in list_users(ix)]


def _check_can_modify_user(ix, user, target_user, target_role):
    if get_global_role(user) != Role.ADMIN:
        required_role = Role.ADMIN if (target_role == Role.ADMIN or get_role(ix, target_user) == Role.ADMIN) else Role.WRITER
        check_role(user, required_role, ix)


@app_index.post("/{ix}/users", status_code=status.HTTP_201_CREATED)
def add_index_users(
        ix: str,
        email: str = Body(..., description="Email address of the user to add"),
        role: RoleType = Body(..., description="Role of the user to add"),
        user: str = Depends(authenticated_user)
):
    """
    Add an existing user to this index.

    To create regular users you need WRITER permission. To create ADMIN users, you need ADMIN permission.
    Global ADMINs can always add users.
    """
    r = Role[role]
    _check_can_modify_user(ix, user, email, r)
    set_role(ix, email, r)
    return {"user": email, "index": ix, "role": r.name}


@app_index.put("/{ix}/users/{email}")
def modify_index_user(
        ix: str,
        email: str,
        role: RoleType = Body(..., description="New role for the user", embed=True),
        user: str = Depends(authenticated_user)
):
    """
    Change the role of an existing user.

    This requires WRITER rights on the index or global ADMIN rights.
    If changing a user from or to ADMIN, it requires (local or global) ADMIN rights
    """
    r = Role[role]
    _check_can_modify_user(ix, user, email, r)
    set_role(ix, email, r)
    return {"user": email, "index": ix, "role": r.name}


@app_index.delete("/{ix}/users/{email}")
def remove_index_user(ix: str, email: str, user: str = Depends(authenticated_user)):
    """
    Remove this user from the index.

    This requires WRITER rights on the index.
    If removing an ADMIN user, it requires ADMIN rights
    """
    _check_can_modify_user(ix, user, email, None)
    remove_role(ix, email)
    return {"user": email, "index": ix, "role": None}


@app_index.get("/{ix}/refresh", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def refresh_index(ix: str):
    refresh(ix)
