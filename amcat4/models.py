from pydantic import BaseModel
from typing import Literal


class SnippetParams(BaseModel):
    """
    Snippet parameters for a specific field.
    nomatch_chars is the number of characters to show if there is no query match. This is always
    the first [nomatch_chars] of the field.
    """

    nomatch_chars: int
    max_matches: int
    match_chars: int


class FieldMetareaderAccess(BaseModel):
    """Metareader access for a specific field."""

    access: Literal["none", "read", "snippet"]
    max_snippet: SnippetParams | None = None


class Field(BaseModel):
    """Settings for a field."""

    type: str
    metareader_access: FieldMetareaderAccess


class UpdateField(BaseModel):
    """Model for updating a field"""

    type: str | None = None
    metareader_access: FieldMetareaderAccess | None = None


def updateField(field: Field, update: UpdateField | Field):
    for key in field.model_fields_set:
        setattr(field, key, getattr(update, key))
    return field
