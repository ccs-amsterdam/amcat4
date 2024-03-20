"""API Endpoints for document and index management."""

from http import HTTPStatus
from typing import Annotated, Any, Literal

import elasticsearch
from elastic_transport import ApiError
from fastapi import APIRouter, HTTPException, Response, status, Depends, Body
from pydantic import BaseModel

from amcat4 import index, fields as index_fields
from amcat4.api.auth import authenticated_user, authenticated_writer, check_role

from amcat4.index import refresh_system_index, remove_role, set_role
from amcat4.fields import field_values, field_stats
from amcat4.models import CreateField, ElasticType, Field, UpdateField

app_index = APIRouter(prefix="/index", tags=["index"])

RoleType = Literal["ADMIN", "WRITER", "READER", "METAREADER"]


@app_index.get("/")
def index_list(current_user: str = Depends(authenticated_user)):
    """
    List index from this server.

    Returns a list of dicts containing name, role, and guest attributes
    """

    def index_to_dict(ix: index.Index) -> dict:
        ix_dict = ix._asdict()
        guest_role_int = ix_dict.get("guest_role", 0)

        ix_dict = dict(id=ix_dict["id"], name=ix_dict["name"], guest_role=index.Role(guest_role_int).name)
        return ix_dict

    return [index_to_dict(ix) for ix in index.list_known_indices(current_user)]


class NewIndex(BaseModel):
    """Form to create a new index."""

    id: str
    name: str | None = None
    guest_role: RoleType | None = None
    description: str | None = None


@app_index.post("/", status_code=status.HTTP_201_CREATED)
def create_index(new_index: NewIndex, current_user: str = Depends(authenticated_writer)):
    """
    Create a new index, setting the current user to admin (owner).

    POST data should be json containing name and optional guest_role
    """
    guest_role = new_index.guest_role and index.Role[new_index.guest_role.upper()]
    try:
        index.create_index(
            new_index.id,
            guest_role=guest_role,
            name=new_index.name,
            description=new_index.description,
            admin=current_user,
        )
    except ApiError as e:
        raise HTTPException(
            status_code=400,
            detail=dict(info=f"Error on creating index: {e}", message=e.message, body=e.body),
        )


# TODO Yes, this should be linked to the actual roles enum
class ChangeIndex(BaseModel):
    """Form to update an existing index."""

    guest_role: Literal["ADMIN", "WRITER", "READER", "METAREADER", "NONE"] | None = "NONE"
    name: str | None = None
    description: str | None = None


@app_index.put("/{ix}")
def modify_index(ix: str, data: ChangeIndex, user: str = Depends(authenticated_user)):
    """
    Modify the index.

    POST data should be json containing the changed values (i.e. name, description, guest_role)

    User needs admin rights on the index
    """
    check_role(user, index.Role.ADMIN, ix)
    guest_role, remove_guest_role = index.Role.NONE, False
    if data.guest_role:
        role = data.guest_role
        if role == "NONE":
            remove_guest_role = True
        else:
            guest_role = index.Role[role]

    index.modify_index(
        ix,
        name=data.name,
        description=data.description,
        guest_role=guest_role,
        remove_guest_role=remove_guest_role,
    )
    refresh_system_index()


@app_index.get("/{ix}")
def view_index(ix: str, user: str = Depends(authenticated_user)):
    """
    View the index.
    """
    try:
        role = check_role(user, index.Role.METAREADER, ix, required_global_role=index.Role.WRITER)
        d = index.get_index(ix)._asdict()
        d["user_role"] = role.name
        d["guest_role"] = index.Role(d.get("guest_role", 0)).name
        d["description"] = d.get("description", "") or ""
        d["name"] = d.get("name", "") or ""
        return d
    except index.IndexDoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} does not exist")


@app_index.delete("/{ix}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_index(ix: str, user: str = Depends(authenticated_user)):
    """Delete the index."""
    check_role(user, index.Role.ADMIN, ix)
    index.delete_index(ix)


@app_index.post("/{ix}/documents", status_code=status.HTTP_201_CREATED)
def upload_documents(
    ix: str,
    documents: Annotated[list[dict[str, Any]], Body(description="The documents to upload")],
    new_fields: Annotated[
        dict[str, CreateField] | None,
        Body(description="If a field in documents does not yet exist, you can create it on the spot"),
    ] = None,
    user: str = Depends(authenticated_user),
):
    """
    Upload documents to this server. Returns a list of ids for the uploaded documents
    """
    check_role(user, index.Role.WRITER, ix)
    return index.upload_documents(ix, documents, new_fields)


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
    fields: Annotated[dict[str, CreateField], Body(description="")],
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
    check_role(user, index.Role.READER, ix)
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


def _check_can_modify_user(ix, user, target_user, target_role):
    if index.get_global_role(user) != index.Role.ADMIN:
        required_role = (
            index.Role.ADMIN
            if (target_role == index.Role.ADMIN or index.get_role(ix, target_user) == index.Role.ADMIN)
            else index.Role.WRITER
        )
        check_role(user, required_role, ix)


@app_index.post("/{ix}/users", status_code=status.HTTP_201_CREATED)
def add_index_users(
    ix: str,
    email: str = Body(..., description="Email address of the user to add"),
    role: RoleType = Body(..., description="Role of the user to add"),
    user: str = Depends(authenticated_user),
):
    """
    Add an existing user to this index.

    To create regular users you need WRITER permission. To create ADMIN users, you need ADMIN permission.
    Global ADMINs can always add users.
    """
    r = index.Role[role]
    _check_can_modify_user(ix, user, email, r)
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

    This requires WRITER rights on the index or global ADMIN rights.
    If changing a user from or to ADMIN, it requires (local or global) ADMIN rights
    """
    r = index.Role[role]
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
    index.refresh_index(ix)
