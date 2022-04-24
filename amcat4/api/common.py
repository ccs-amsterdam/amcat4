from fastapi import HTTPException, status

from amcat4.index import Index


def _index(ix: str) -> Index:
    try:
        return Index.get(Index.name == ix)
    except Index.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} not found")
