import elasticsearch.helpers
from amcat4.config import get_settings
from pydantic import BaseModel
from typing import Iterable
from amcat4.elastic_mapping import ElasticMapping
from amcat4.elastic_connection import _elastic_connection


class SystemIndex(BaseModel):
    name: str
    mapping: ElasticMapping


def system_index_name(version: int, path: str) -> str:
    """
    Get the full name for the system index, based on the version and path.
    (version and path are optional because the first version
    didn't have versions and only one path)
    """
    index = get_settings().system_index
    if version > 1:
        index = f"{index}_V{version}"
    if path:
        index = f"{index}_{path}"
    return index


class BulkInsertAction(BaseModel):
    index: str
    id: str | None
    doc: dict


def bulk_insert(generator: Iterable[BulkInsertAction], batchsize: int = 1000) -> None:
    """
    Insert documents into indices in bulk. Input is a generator
    that yields BulkInsertDoc objects, which need to include the
    index name, optional id (random if empty), and the document to insert.
    """
    actions: list[dict] = []
    for item in generator:
        actions.append({"_index": item.index, "_id": item.id, "_source": item.doc})

        if len(actions) >= batchsize:
            elasticsearch.helpers.bulk(_elastic_connection(), actions)
            actions = []

    if len(actions) > 0:
        elasticsearch.helpers.bulk(_elastic_connection(), actions)



def batched_index_scan(
    index: str, batchsize: int = 1000, scroll: str = "5m"
) -> Iterable[(int, dict)]:
    """
    Scan an index in batches of the given size.
    Yields documents one by one.
    """
    for hit in elasticsearch.helpers.scan(
        _elastic_connection(), index=index, scroll=scroll, size=batchsize, _source=True
    ):
        yield hit["_id"], hit["_source"]
