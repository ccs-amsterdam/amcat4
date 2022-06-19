"""Helper methods for the API."""

from fastapi import HTTPException, status
from pydantic.main import BaseModel

from amcat4.auth import User
from amcat4.index import Index, IndexRole


def _index(ix: str) -> Index:
    try:
        return Index.get(Index.name == ix)
    except Index.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} not found")


def py2dict(m: BaseModel) -> dict:
    """Convert a pydantic object to a regular dict."""
    return {k: v for (k, v) in m.dict().items() if v is not None}


def get_user_or_404(email: str) -> User:
    """Get a user or raise an HTTP 404."""
    try:
        return User.get(User.email == email)
    except User.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"User {email} does not exist")


def get_indexrole_or_404(email: str, index: str) -> IndexRole:
    """Get an IndexRole or raise a 404."""
    u = get_user_or_404(email)
    ix = _index(index)
    try:
        return IndexRole.get(IndexRole.user == u, IndexRole.index == ix)
    except IndexRole.DoesNotExist:
        raise HTTPException(status_code=404, detail=f"User {email} does not exist in index {index}")
