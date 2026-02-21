from typing import Any, AsyncGenerator, AsyncIterable, Iterable, Literal, Tuple

import elasticsearch.helpers
from elasticsearch.helpers.errors import BulkIndexError
from pydantic import BaseModel

from amcat4.config import get_settings
from amcat4.connections import es
from amcat4.elastic.mapping import ElasticMapping
from amcat4.models import IndexId


class SystemIndexMapping(BaseModel):
    name: IndexId | Literal[""]
    mapping: ElasticMapping


## TODO: fix the entire mess with the amcat prefix...


def system_index_name(version: int, path: str) -> str:
    """
    Get the full name for the system index, based on the version and path.
    (version and path are optional because the first version
    didn't have versions and only one path)
    """
    index = get_settings().system_index
    test_mode = get_settings().test_mode

    if test_mode:
        index = f"testdb_{index}"
    if version > 1:
        index = f"{index}_v{version}"
    if path != "":
        index = f"{index}_{path}"
    return index


class BulkInsertAction(BaseModel):
    index: str
    id: str | None
    doc: dict


async def es_get(index: str, id: str) -> dict | None:
    return (await es().get(index=index, id=id))["_source"]


async def es_upsert(index: str, id: str, doc: dict, refresh: bool = True) -> None:
    await es().update(index=index, id=id, doc=doc, doc_as_upsert=True, refresh=refresh)


async def es_bulk_create(
    generator: AsyncGenerator[BulkInsertAction, None], batchsize: int = 1000, overwrite: bool = False
) -> None:
    op_type = "index" if overwrite else "create"
    return await es_bulk_action(generator, op_type=op_type, batchsize=batchsize)


async def es_bulk_upsert(generator: AsyncGenerator[BulkInsertAction, None], batchsize: int = 1000) -> None:
    return await es_bulk_action(generator, op_type="update", batchsize=batchsize)


async def es_bulk_action(
    generator: AsyncGenerator[BulkInsertAction, None],
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
        for id, doc in index_scan("my_index"):
            if doc.get("somefield") == "somevalue":
                yield BulkInsertAction(index="another_index", id=id, doc=doc)
            if doc.get("otherfield") == "othervalue":
                yield BulkInsertAction(index="yet_another_index", id=id, doc=doc)
    es_bulk_upsert(gen())

    about op_type:
        - use "index" to create or overwrite documents
        - use "create" to create documents, fail if they already exist
        - use "update" to create or update documents (i.e. upsert)
    """
    actions: list[dict] = []
    async for item in generator:
        action: dict = {"_op_type": op_type, "_index": item.index, "_id": item.id}

        if op_type == "update":
            action["doc"] = item.doc
            action["doc_as_upsert"] = True
        else:
            action = {**item.doc, **action}
        actions.append(action)

        if len(actions) >= batchsize:
            await bulk_helper_with_errors(actions, refresh=refresh)
            actions = []

    if len(actions) > 0:
        await bulk_helper_with_errors(actions, refresh=refresh)


async def bulk_helper_with_errors(actions: Iterable[dict], **kwargs) -> None:
    """
    elastic bulk but printing the reason for the first error if any
    """
    try:
        await elasticsearch.helpers.async_bulk(es(), actions, stats_only=False, **kwargs)

    except BulkIndexError as e:
        if e.errors:
            _, error = list(e.errors[0].items())[0]
            reason = error.get("error", {}).get("reason", error)
            e.args = e.args + (f"First error: {reason}",)
        raise


async def index_scan(
    index: str,
    batchsize: int = 1000,
    query: dict | None = None,
    sort: dict | None = None,
    source: list[str] | None = None,
    exclude_source: list[str] | None = None,
    scroll: str = "5m",
) -> AsyncIterable[tuple[str, dict]]:
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
        query_body["_source_includes"] = source
    if exclude_source is not None:
        query_body["_source_excludes"] = exclude_source
    async for hit in elasticsearch.helpers.async_scan(
        es(),
        index=index,
        query=query_body,
        scroll=scroll,
        size=batchsize,
        preserve_order=sort is not None,
    ):
        yield hit["_id"], hit["_source"]


async def batched_index_scan(
    index: str,
    batchsize: int = 1000,
    query: dict | None = None,
    sort: dict | None = None,
    source: list[str] | None = None,
    exclude_source: list[str] | None = None,
    scroll: str = "5m",
    scroll_id: str | None = None,
) -> tuple[str | None, list[Tuple[str, dict[str, Any]]]]:
    """
    Like index scan, but returns a batch at a time and a scroll id for manual scrolling
    """
    if scroll_id is None:
        res = await es().search(
            index=index,
            query=query,
            sort=sort,
            source_includes=source,
            source_excludes=exclude_source,
            scroll=scroll,
            size=batchsize,
        )
    else:
        res = await es().scroll(scroll_id=scroll_id, scroll=scroll)

    new_scroll_id: str | None = res.get("_scroll_id", None)
    hits = res["hits"]["hits"]

    if not hits:
        if new_scroll_id:
            await es().clear_scroll(scroll_id=new_scroll_id)
        return None, []

    batch_data: list[Tuple[str, dict[str, Any]]] = [(hit["_id"], hit["_source"]) for hit in hits]

    return new_scroll_id, batch_data
