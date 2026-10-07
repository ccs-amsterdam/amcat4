"""API Endpoints for index field management."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from amcat4.api.auth_helpers import authenticated_user
from amcat4.errors import NotFoundError
from amcat4.models import CreateDocumentField, DocumentField, FieldType, IndexId, Roles, UpdateDocumentField, User
from amcat4.systemdata.fields import (
    create_fields,
    delete_fields,
    field_access,
    field_stats,
    field_values,
    list_fields,
    update_fields,
)
from amcat4.systemdata.roles import HTTPException_if_not_project_index_role

app_index_fields = APIRouter(prefix="", tags=["project index fields"])


@app_index_fields.post("/index/{ix}/fields", status_code=status.HTTP_204_NO_CONTENT)
async def add_fields(
    ix: IndexId,
    fields: Annotated[
        dict[str, FieldType | CreateDocumentField],
        Body(
            description="Either a dictionary that maps field names to field specifications"
            "({field: {type: 'keyword', unique: True }}), "
            "or a simplified version that only specifies the type ({field: type})"
        ),
    ],
    user: User = Depends(authenticated_user),
):
    """
    Create one or more fields in an index. Requires WRITER role on the index.
    """
    await HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
    await create_fields(ix, fields)


@app_index_fields.get("/index/{ix}/fields")
async def get_project_fields(ix: IndexId, user: User = Depends(authenticated_user)) -> dict[str, DocumentField]:
    """
    Get the fields (columns) used in this index. Requires METAREADER role on the index.
    """
    await HTTPException_if_not_project_index_role(user, ix, Roles.METAREADER)
    try:
        return await list_fields(ix)
    except NotFoundError:
        raise HTTPException(404, f"Project {ix} does not exist, sorry")


@app_index_fields.put("/index/{ix}/fields", status_code=status.HTTP_204_NO_CONTENT)
async def modify_fields(
    ix: IndexId,
    fields: Annotated[dict[str, UpdateDocumentField], Body(description="")],
    user: User = Depends(authenticated_user),
):
    """
    Update the settings of one or more fields. Requires WRITER role on the index.
    A field can be renamed by giving a new name, and converted to another type by giving a new type
    (this fails if any value cannot be converted).
    """
    await HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
    await update_fields(ix, fields)


async def _HTTPException_if_not_visible(user: User, ix: IndexId, field: str) -> None:
    """Field values and statistics can be requested by users who can see the (full) field values"""
    spec = (await field_access(user, [ix])).visible.get(field)
    if spec is None or spec.snippet is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"{user.email or 'GUEST'} cannot access field {field} on index {ix}")


@app_index_fields.delete("/index/{ix}/fields", status_code=status.HTTP_204_NO_CONTENT)
async def remove_fields(
    ix: IndexId,
    fields: Annotated[list[str], Body(description="The names of the fields to delete")],
    user: User = Depends(authenticated_user),
):
    """
    Delete fields, including their values in all documents. Requires WRITER role on the index.
    Fails (and deletes nothing) if removing a unique field would make documents duplicates.
    """
    await HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
    await delete_fields(ix, fields)


@app_index_fields.get("/index/{ix}/fields/{field}/values")
async def get_field_values(
    ix: IndexId,
    field: str,
    size: int = Query(200, ge=1, le=2000, description="Maximum number of values to return"),
    user: User = Depends(authenticated_user),
) -> list[Any]:
    """
    Get the most frequent values of a keyword or tag field, most frequent first.
    Requires that the user can see the field values.
    """
    await _HTTPException_if_not_visible(user, ix, field)
    return await field_values(ix, field, size=size)


@app_index_fields.get("/index/{ix}/fields/{field}/stats")
async def get_field_stats(ix: IndexId, field: str, user: User = Depends(authenticated_user)) -> dict[str, Any]:
    """
    Get the number of documents with a value, and the min, max and average value of a number or date field.
    Requires that the user can see the field values.
    """
    await _HTTPException_if_not_visible(user, ix, field)
    return await field_stats(ix, field)
