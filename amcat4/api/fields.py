from http import HTTPStatus
from typing import Annotated, Mapping, Optional, cast, get_args

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from pydantic import BaseModel

from amcat4 import fields as index_fields
from amcat4 import index
from amcat4.api.auth import authenticated_user, check_role
from amcat4.fields import field_stats, field_values
from amcat4.models import Field, FieldType, FieldValue, PartialField

app_fields = APIRouter(prefix="/index", tags=["fields"])


def standardize_fields(fields: Mapping[str, FieldType | PartialField]) -> Mapping[str, PartialField]:
    """Convert FieldTypes into PartialFields"""
    sfields = {}
    for k, v in fields.items():
        if isinstance(v, str):
            assert v in get_args(FieldType), f"Unknown amcat type {v}"
            sfields[k] = PartialField(type=cast(FieldType, v))
        else:
            sfields[k] = v
    return sfields


@app_fields.put("/{ix}/fields")
@app_fields.post("/{ix}/fields")
def set_fields(
    ix: str,
    fields: Annotated[
        Mapping[str, FieldType | PartialField],
        Body(
            description="Either a dictionary that maps field names to field specifications"
            "({field: {type: 'text', identifier: True }}), "
            "or a simplified version that only specifies the type ({field: type})"
        ),
    ],
    user: str = Depends(authenticated_user),
):
    """
    Set (create or modify) fields
    """
    check_role(user, index.Role.WRITER, ix)
    fields = standardize_fields(fields)
    index_fields.set_fields(ix, fields)
    return "", HTTPStatus.NO_CONTENT


@app_fields.get("/{ix}/fields")
def get_fields(ix: str, user: str = Depends(authenticated_user)):
    """
    Get the fields (columns) used in this index.

    Returns a json array of {name, type} objects
    """
    check_role(user, index.Role.METAREADER, ix)
    return {name: field.model_dump() for (name, field) in index.get_fields(ix).items()}


@app_fields.get("/{ix}/fields/{field}/values")
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


@app_fields.get("/{ix}/fields/{field}/stats")
def get_field_stats(ix: str, field: str, user: str = Depends(authenticated_user)):
    """Get statistics for a specific value. Only works for numeric (incl date) fields."""
    check_role(user, index.Role.READER, ix)
    return field_stats(ix, field)


@app_fields.get("/{index}/fields/values")
def get_all_fields_values() -> list[FieldValue]:
    return []
