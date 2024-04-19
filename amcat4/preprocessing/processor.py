import asyncio
from functools import cache
import logging
from typing import Dict, Tuple
from elasticsearch import NotFoundError
from httpx import AsyncClient, HTTPStatusError
from amcat4.elastic import es
from amcat4.index import list_known_indices, refresh_index, update_document
from amcat4.preprocessing.models import PreprocessingInstruction

logger = logging.getLogger("amcat4.preprocessing")


class PreprocessorManager:
    SINGLETON = None

    def __init__(self):
        self.preprocessors: Dict[Tuple[str, str], asyncio.Task] = {}
        self.preprocessor_status: Dict[Tuple[str, str], str] = {}

    def add_preprocessor(self, index: str, instruction: PreprocessingInstruction):
        self.preprocessors[index, instruction.field] = asyncio.create_task(run_processor_loop(index, instruction))

    def stop_preprocessor(self, index: str, field: str):
        self.preprocessors[index, field].cancel()

    def stop_preprocessors(self, index: str):
        tasks = list(self.preprocessors.items())
        for (ix, field), task in tasks:
            if index == ix:
                task.cancel()
            del self.preprocessors[ix, field]
            del self.preprocessor_status[ix, field]

    def stop(self):
        for task in self.preprocessors.values():
            task.cancel()

    def get_status(self, index: str, field: str):
        task = self.preprocessors.get((index, field))
        if not task:
            return "Unknown"
        if task.cancelled():
            return "Cancelled"
        if task.done():
            return "Stopped"
        return self.preprocessor_status.get((index, field), "Unknown status")


@cache
def get_manager():
    return PreprocessorManager()


def start_processors():
    import amcat4.preprocessing.instruction

    logger.info("Starting preprocessing loops (if needed)")
    manager = get_manager()
    for index in list_known_indices():
        try:
            instructions = list(amcat4.preprocessing.instruction.get_instructions(index.id))
        except NotFoundError:
            logging.warning(f"Index {index.id} does not exist!")
            continue
        for instruction in instructions:
            manager.add_preprocessor(index.id, instruction)


async def run_processor_loop(index, instruction: PreprocessingInstruction):
    logger.info(f"Starting preprocessing loop for {index}.{instruction.field}")
    while True:
        try:
            logger.info(f"Preprocessing loop woke up for {index}.{instruction.field}")
            get_manager().preprocessor_status[index, instruction.field] = "Active"
            await process_documents(index, instruction)
            get_manager().preprocessor_status[index, instruction.field] = "Sleeping"
            logger.info(f"Preprocessing loop sleeping for {index}.{instruction.field}")
        except Exception:
            logger.exception(f"Error on preprocessing {index}.{instruction.field}")
        await asyncio.sleep(10)


async def process_documents(index: str, instruction: PreprocessingInstruction, size=100):
    """
    Process all currently to-do documents in the index for this instruction.
    Returns when it runs out of documents to do
    """
    # Q: it it better to repeat a simple "get n todo docs", or to iteratively scroll past all todo items?
    while True:
        docs = list(get_todo(index, instruction, size=size))
        logger.debug(f"Preprocessing for {index}.{instruction.field}: retrieved {len(docs)} docs to process")
        for doc in docs:
            await process_doc(index, instruction, doc)
        if len(docs) < size:
            return
        refresh_index(index)


def get_todo(index: str, instruction: PreprocessingInstruction, size=100):
    fields = [arg.field for arg in instruction.arguments if arg.field]
    q = dict(bool=dict(must_not=dict(exists=dict(field=instruction.field))))
    for doc in es().search(index=index, size=size, source_includes=fields, query=q)["hits"]["hits"]:
        yield {"_id": doc["_id"], **doc["_source"]}


def get_counts(index: str, field: str):
    agg = dict(status=dict(terms=dict(field=f"{field}.status")))

    res = es().search(index=index, size=0, aggs=agg)
    result = dict(total=res["hits"]["total"]["value"])
    for bucket in res["aggregations"]["status"]["buckets"]:
        result[bucket["key"]] = bucket["doc_count"]
    return result


async def process_doc(index: str, instruction: PreprocessingInstruction, doc: dict):
    # TODO catch errors and add to status field, rather than raising
    try:
        req = instruction.build_request(index, doc)
    except Exception as e:
        logging.exception(f"Error on preprocessing {index}.{instruction.field} doc {doc['_id']}")
        update_document(index, doc["_id"], {instruction.field: dict(status="error", error=str(e))})
    try:
        response = await AsyncClient().send(req)
        response.raise_for_status()
    except HTTPStatusError as e:
        error = f"{e.response.status_code}: {e.response.text}"
        logging.exception(f"Error on preprocessing {index}.{instruction.field} doc {doc['_id']}")
        update_document(index, doc["_id"], {instruction.field: dict(status="error", error=error)})
        return
    result = dict(instruction.parse_output(response.json()))
    result[instruction.field] = dict(status="done")
    update_document(index, doc["_id"], result)
