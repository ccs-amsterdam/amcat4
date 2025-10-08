from pydantic.main import BaseModel
from amcat4.system_index.specifications import v2
from amcat4.system_index.util import SINGLE_DOC_INDEX_ID, create_or_refresh_system_index, safe_write_to_system_index, get_system_index_name, refresh_index
from amcat4.elastic_connection import _elastic_connection
from typing import Any

# HERE WE DEFINE THE CURRENT SYSTEM INDEX VERSION
SPEC = v2.SPEC

class InvalidSystemIndex(Exception):
    pass


def setup_system_index() -> None:
    create_or_refresh_system_index(SPEC)



def get_from_system_index(path: str, id: str | None = None, sources: list[str] | None = None) -> dict | None:
    """
    Get a document from the system index at the given path by its ID.
    For an index that only contains a single document (like system_settings), the ID can be omitted.
    """
    params: dict[str,Any] = {
        "index": get_system_index_name(SPEC.version, path),
        "id": id if id else SINGLE_DOC_INDEX_ID,
    }

    if sources is not None:
        params['source_includes'] = sources

    doc = _elastic_connection().get(**params)
    return doc["_source"] if doc["found"] else None


def query_from_system_index(path: str, query: dict, size: int = 1000, sources: list[str] | None = None) -> list[dict]:
    params: dict[str,Any] = {
        "index": get_system_index_name(SPEC.version, path),
        "query": query,
        "size": size,
    }

    if sources is not None:
        params['source_includes'] = sources

    res = _elastic_connection().search(**params)
    return [hit["_source"] for hit in res["hits"]["hits"]]


def insert_to_system_index(path: str, doc: dict | list[dict], refresh: bool = True) -> None:
    """
    Insert a document or list of documents into the system index at the given path.
    This will validate the full document(s) against the system index specification before inserting.
    """
    safe_write_to_system_index(SPEC, path, doc, op_type="index", refresh=refresh)


def update_system_index(path: str, doc: dict | list[dict], refresh: bool = True) -> None:
    """
    Update a document or list of documents in the system index at the given path.
    This will validate only the given fields in the documents against the system
    index specification. Will raise an error if the document does not already exist.
    """
    safe_write_to_system_index(SPEC, path, doc, op_type="update", refresh=refresh)
