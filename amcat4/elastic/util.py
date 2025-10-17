import elasticsearch.helpers
from amcat4.config import get_settings
from pydantic import BaseModel
from typing import Iterable, Literal
from amcat4.elastic.mapping import ElasticMapping
from amcat4.elastic.connection import elastic_connection


class SystemIndexMapping(BaseModel):
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
    if path != "":
        index = f"{index}_{path}"
    return index


class BulkInsertAction(BaseModel):
    index: str
    id: str | None
    doc: dict


def es_get(index: str, id: str) -> dict | None:
    return elastic_connection().get(index=index, id=id)["_source"]


def es_upsert(index: str, id: str, doc: dict, refresh: bool = True) -> None:
    elastic_connection().update(index=index, id=id, doc=doc, doc_as_upsert=True, refresh=refresh)


def es_bulk_create_or_overwrite(generator: Iterable[BulkInsertAction], batchsize: int = 1000) -> None:
    return es_bulk_action(generator, op_type="index", batchsize=batchsize)


def es_bulk_upsert(generator: Iterable[BulkInsertAction], batchsize: int = 1000) -> None:
    return es_bulk_action(generator, op_type="update", batchsize=batchsize)


def es_bulk_action(
    generator: Iterable[BulkInsertAction],
    op_type: Literal["index", "create", "update"],
    batchsize: int = 1000,
    refresh: bool = True,
) -> None:
    """
    Insert documents into indices in bulk. Input is a generator
    that yields BulkInsertDoc objects, which need to include the
    index name, optional id (random if empty), and the document to insert.

    Works nicely together with batched_index_scan for moving stuff around (e.g. in migrations),
    because this automatically batches both the scan and the insert.

    def gen():
        for id, doc in batched_index_scan("my_index"):
            if doc.get("somefield") == "somevalue":
                yield BulkInsertAction(index="another_index", id=id, doc=doc)
            if doc.get("otherfield") == "othervalue":
                yield BulkInsertAction(index="yet_another_index", id=id, doc=doc)
    bulk_action(gen())

    about op_type:
        - use "index" to create or overwrite documents
        - use "create" to create documents, fail if they already exist
          (preferred in migrations for speed and safety)
        - use "update" to create or update documents (preferred in normal use to
          avoid data loss, and we should always validate input with pydantic anyway)
    """
    actions: list[dict] = []
    for item in generator:
        action: dict = {"_op_type": op_type, "_index": item.index, "_id": item.id}

        if op_type == "update":
            action["doc"] = item.doc
            action["doc_as_upsert"] = True
        else:
            action = {**item.doc, **action}
        actions.append(action)

        if len(actions) >= batchsize:
            elasticsearch.helpers.bulk(elastic_connection(), actions, refresh=refresh)
            actions = []

    if len(actions) > 0:
        elasticsearch.helpers.bulk(elastic_connection(), actions, refresh=refresh)


def index_scan(
    index: str,
    batchsize: int = 1000,
    query: dict | None = None,
    sort: dict | None = None,
    source: list[str] | None = None,
    scroll: str = "5m",
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
        elastic_connection(),
        index=index,
        query=query_body,
        scroll=scroll,
        size=batchsize,
        preserve_order=sort is not None,
    ):
        yield hit["_id"], hit["_source"]
