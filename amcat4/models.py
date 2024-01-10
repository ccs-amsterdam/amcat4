from pydantic import BaseModel
from typing import Optional


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

    access: bool
    max_snippet: Optional[SnippetParams]


class FieldSettings(BaseModel):
    """Settings for a field."""

    metareader_access: Optional[FieldMetareaderAccess] = None


def updateFieldSettings(field: FieldSettings, update: FieldSettings):
    for key in field.model_fields_set:
        setattr(field, key, getattr(update, key))
    return field
