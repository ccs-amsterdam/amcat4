import pydantic
from pydantic import BaseModel
from typing import Annotated, Literal


class SnippetParams(BaseModel):
    """
    Snippet parameters for a specific field.
    nomatch_chars is the number of characters to show if there is no query match. This is always
    the first [nomatch_chars] of the field.
    """

    nomatch_chars: Annotated[int, pydantic.Field(ge=1)] = 1
    max_matches: Annotated[int, pydantic.Field(ge=0)] = 0
    match_chars: Annotated[int, pydantic.Field(ge=1)] = 1


class FieldClientDisplay(BaseModel):
    """Client display settings for a specific field."""

    in_list: bool = False
    in_document: bool = True


class FieldMetareaderAccess(BaseModel):
    """Metareader access for a specific field."""

    access: Literal["none", "read", "snippet"] = "none"
    max_snippet: SnippetParams | None = None


class Field(BaseModel):
    """Settings for a field."""

    type: str
    metareader: FieldMetareaderAccess = FieldMetareaderAccess()
    client_display: FieldClientDisplay = FieldClientDisplay()


class UpdateField(BaseModel):
    """Model for updating a field"""

    type: str | None = None
    metareader: FieldMetareaderAccess | None = None
    client_display: FieldClientDisplay | None = None


def updateField(field: Field, update: UpdateField | Field):
    for key in update.model_fields_set:
        setattr(field, key, getattr(update, key))
    return field


FilterValue = str | int


class FilterSpec(BaseModel):
    """Form for filter specification."""

    values: list[FilterValue] | None = None
    gt: FilterValue | None = None
    lt: FilterValue | None = None
    gte: FilterValue | None = None
    lte: FilterValue | None = None
    exists: bool | None = None


class FieldSpec(BaseModel):
    """Form for field specification."""

    name: str
    snippet: SnippetParams | None = None


class SortSpec(BaseModel):
    """Form for sort specification."""

    order: Literal["asc", "desc"] = "asc"
