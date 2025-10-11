import elasticsearch.helpers
import json
import hashlib
from pydantic import BaseModel
from typing import Iterable
from amcat4.elastic_connection import _elastic_connection

class BulkInsertAction(BaseModel):
    index: str
    id: str | None
    doc: dict


def bulk_insert(generator: Iterable[BulkInsertAction], batchsize: int = 1000) -> None:
    """
    Insert documents into indices in bulk. Input is a generator
    that yields BulkInsertDoc objects, which need to include the
    index name, optional id (random if empty), and the document to insert.

    Works nicely together with batched_index_scan for moving stuff around in migrations,
    because this automatically batches both the scan and the insert.

    def gen():
        for id, doc in batched_index_scan("my_index"):
            if doc.get("somefield") == "somevalue":
                yield BulkInsertAction(index="another_index", id=id, doc=doc)
            if doc.get("otherfield") == "othervalue":
                yield BulkInsertAction(index="yet_another_index", id=id, doc=doc)
    bulk_insert(gen())
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
    index: str, batchsize: int = 1000, query: dict | None = None,
    sort: dict | None = None, source: list[str] | None = None, scroll: str = "5m"
) -> Iterable[tuple[str, dict]]:
    """
    Scan an index in batches of the given size. Yields documents one by one (batching behind the scenes).
    Helpers scan is much faster without sorting (which sets preserve_order to TRUE), so avoid it if you can.
    """

    query_body = {}
    if query is not None:
        query_body["query"] = query
    if sort is not None:
        query_body["sort"] = sort
    if source is not None:
        query_body["_source"] = source

    for hit in elasticsearch.helpers.scan(
        _elastic_connection(), index=index, query=query_body,
        scroll=scroll, size=batchsize, preserve_order=sort is not None
    ):
        yield hit["_id"], hit["_source"]



def create_id(document: dict, identifiers: list[str]) -> str:
    """
    Create the _id for a document.
    """

    if len(identifiers) == 0:
        raise ValueError("Can only create id if identifiers are specified")

    id_keys = sorted(set(identifiers) & set(document.keys()))
    id_fields = {k: document[k] for k in id_keys}
    hash_str = json.dumps(id_fields, sort_keys=True, ensure_ascii=True, default=str).encode("ascii")
    m = hashlib.sha224()
    m.update(hash_str)
    return m.hexdigest()
