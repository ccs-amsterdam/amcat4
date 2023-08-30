"""Helper methods for the API."""

from pydantic.main import BaseModel


def py2dict(m: BaseModel) -> dict:
    """Convert a pydantic object to a regular dict."""
    return {k: v for (k, v) in m.model_dump().items() if v is not None}
