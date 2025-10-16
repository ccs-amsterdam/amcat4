"""API Endpoints for document and index management."""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status

from amcat4.api.auth import authenticated_user
from amcat4.models import (
    CreateField,
    FieldSpec,
    FieldType,
    Role,
    UpdateField,
    User,
)
from amcat4.systemdata import fields as _fields
from amcat4.systemdata.roles import get_project_index_role, raise_if_not_project_index_role, role_is_at_least

app_index = APIRouter(prefix="/index", tags=["index"])


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
    user: User = Depends(authenticated_user),
):
    """
    Create fields
    """
    raise_if_not_project_index_role(user, ix, Role.WRITER)

    _fields.create_fields(ix, fields)
    return "", HTTPStatus.NO_CONTENT


@app_index.get("/{ix}/fields")
def get_fields(ix: str, user: User = Depends(authenticated_user)):
    """
    Get the fields (columns) used in this index.

    Returns a json array of {name, type} objects
    """
    raise_if_not_project_index_role(user, ix, Role.METAREADER)
    return _fields.get_fields(ix)


@app_index.put("/{ix}/fields")
def update_fields(
    ix: str, fields: Annotated[dict[str, UpdateField], Body(description="")], user: User = Depends(authenticated_user)
):
    """
    Update the field settings
    """
    raise_if_not_project_index_role(user, ix, Role.WRITER)

    _fields.update_fields(ix, fields)
    return "", HTTPStatus.NO_CONTENT


@app_index.get("/{ix}/fields/{field}/values")
def get_field_values(ix: str, field: str, user: User = Depends(authenticated_user)):
    """
    Get unique values for a specific field. Should mainly/only be used for tag fields.
    Main purpose is to provide a list of values for a dropdown menu.

    TODO: at the moment 'only' returns top 2000 values. Currently throws an
    error if there are more than 2000 unique values. We can increase this limit, but
    there should be a limit. Querying could be an option, but not sure if that is
    efficient, since elastic has to aggregate all values first.
    """
    raise_if_not_project_index_role(user, ix, Role.READER)
    values = _fields.field_values(ix, field, size=2001)
    if len(values) > 2000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Field {field} has more than 2000 unique values",
        )
    return values


@app_index.get("/{ix}/fields/{field}/stats")
def get_field_stats(ix: str, field: str, user: User = Depends(authenticated_user)):
    """Get statistics for a specific value. Only works for numeric (incl date) fields."""
    role = get_project_index_role(user.email, ix)
    if role_is_at_least(role, Role.READER):
        return _fields.field_stats(ix, field)
    elif role_is_at_least(role, Role.METAREADER):
        _fields.raise_if_field_not_allowed(ix, user, [FieldSpec(name=field)])
        return _fields.field_stats(ix, field)
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User {user.email} cannot access field stats for index {ix}. Required role: METAREADER",
        )
