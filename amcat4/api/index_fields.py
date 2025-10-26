"""API Endpoints for index field management."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field

from amcat4.api.auth import authenticated_user
from amcat4.models import (
    CreateDocumentField,
    FieldSpec,
    FieldType,
    IndexId,
    Roles,
    UpdateDocumentField,
    User,
    DocumentField,
)
from amcat4.systemdata.fields import (
    HTTPException_if_invalid_field_access,
    create_fields,
    field_stats,
    field_values,
    list_fields,
    update_fields,
)
from amcat4.systemdata.roles import get_user_project_role, HTTPException_if_not_project_index_role, role_is_at_least

app_index_fields = APIRouter(prefix="", tags=["project index fields"])


# RESPONSE MODELS
class FieldListResponse(BaseModel):
    """A list of fields in the index."""

    name: str = Field(..., description="The name of the field.")
    type: FieldType = Field(..., description="The type of the field.")


class FieldValuesResponse(BaseModel):
    """A list of unique values for a field."""

    values: list[Any] = Field(..., description="The unique values for the field.")


class FieldStatsResponse(BaseModel):
    """Statistics for a numeric field."""

    stats: dict = Field(..., description="A dictionary of statistics for the field.")


@app_index_fields.post("/index/{ix}/fields", status_code=status.HTTP_204_NO_CONTENT)
def add_fields(
    ix: IndexId,
    fields: Annotated[
        dict[str, FieldType | CreateDocumentField],
        Body(
            description="Either a dictionary that maps field names to field specifications"
            "({field: {type: 'text', identifier: True }}), "
            "or a simplified version that only specifies the type ({field: type})"
        ),
    ],
    user: User = Depends(authenticated_user),
):
    """
    Create one or more fields in an index. Requires WRITER role on the index.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
    create_fields(ix, fields)


@app_index_fields.get("/index/{ix}/fields")
def get_project_fields(ix: IndexId, user: User = Depends(authenticated_user)) -> dict[str, DocumentField]:
    """
    Get the fields (columns) used in this index. Requires METAREADER role on the index.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.METAREADER)
    return list_fields(ix)


@app_index_fields.put("/index/{ix}/fields", status_code=status.HTTP_204_NO_CONTENT)
def modify_fields(
    ix: IndexId,
    fields: Annotated[dict[str, UpdateDocumentField], Body(description="")],
    user: User = Depends(authenticated_user),
):
    """
    Update the settings of one or more fields. Requires WRITER role on the index.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
    update_fields(ix, fields)


@app_index_fields.get("/index/{ix}/fields/{field}/values")
def get_field_values(ix: IndexId, field: str, user: User = Depends(authenticated_user)) -> list[Any]:
    """
    Get unique values for a specific field. Requires READER role on the index.

    This is intended for fields with a limited number of unique values (e.g., tag fields).
    It will return an error if the field has more than 2000 unique values.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.READER)
    values = field_values(ix, field, size=2001)
    if len(values) > 2000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Field {field} has more than 2000 unique values",
        )
    return values


@app_index_fields.get("/index/{ix}/fields/{field}/stats")
def get_field_stats(ix: IndexId, field: str, user: User = Depends(authenticated_user)):
    """Get statistics for a specific field. Only works for numeric (incl date) fields. Requires READER or METAREADER role."""
    role = get_user_project_role(user, ix)
    if role_is_at_least(role, Roles.READER):
        return field_stats(ix, field)
    elif role_is_at_least(role, Roles.METAREADER):
        fields = list_fields(ix)
        if fields[field].metareader.access != "read":
            raise HTTPException(403, detail=f"User {user.email} cannot access field stats for field {field} in index {ix}")
        return field_stats(ix, field)
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User {user.email} cannot access field stats for index {ix}. Required role: METAREADER",
        )
