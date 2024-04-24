import asyncio
from functools import cache
import logging
from typing import Dict, Literal, Tuple
from elasticsearch import NotFoundError
from httpx import AsyncClient, HTTPStatusError
from amcat4.elastic import es
import amcat4.index
from amcat4.preprocessing.models import PreprocessingInstruction

logger = logging.getLogger("amcat4.preprocessing")

PreprocessorStatus = Literal["Active", "Paused", "Unknown", "Error", "Stopped", "Done"]


class RateLimit(Exception):
    pass


PAUSE_ON_RATE_LIMIT_SECONDS = 10


class PreprocessorManager:
    SINGLETON = None

    def __init__(self):
        self.preprocessors: Dict[Tuple[str, str], PreprocessingInstruction] = {}
        self.running_tasks: Dict[Tuple[str, str], asyncio.Task] = {}
        self.preprocessor_status: Dict[Tuple[str, str], PreprocessorStatus] = {}

    def set_status(self, index: str, field: str, status: PreprocessorStatus):
        self.preprocessor_status[index, field] = status

    def add_preprocessor(self, index: str, instruction: PreprocessingInstruction):
        """Start a new preprocessor task and add it to the manager, returning the Task object"""
        self.preprocessors[index, instruction.field] = instruction
        self.start_preprocessor(index, instruction.field)

    def start_preprocessor(self, index: str, field: str):
        if existing_task := self.running_tasks.get((index, field)):
            if not existing_task.done:
                return existing_task
        instruction = self.preprocessors[index, field]
        task = asyncio.create_task(run_processor_loop(index, instruction))
        self.running_tasks[index, instruction.field] = task

    def start_index_preprocessors(self, index: str):
        for ix, field in self.preprocessors:
            if ix == index:
                self.start_preprocessor(index, field)

    def stop_preprocessor(self, index: str, field: str):
        """Stop a preprocessor task"""
        try:
            if task := self.running_tasks.get((index, field)):
                task.cancel()
        except:
            logger.exception(f"Error on cancelling preprocessor {index}:{field}")

    def remove_preprocessor(self, index: str, field: str):
        """Stop this preprocessor remove them from the manager"""
        self.stop_preprocessor(index, field)
        del self.preprocessor_status[index, field]
        del self.preprocessors[index, field]

    def remove_index_preprocessors(self, index: str):
        """Stop all preprocessors on this index and remove them from the manager"""
        for ix, field in list(self.preprocessors.keys()):
            if index == ix:
                self.remove_preprocessor(ix, field)

    def get_status(self, index: str, field: str) -> PreprocessorStatus:
        status = self.preprocessor_status.get((index, field), "Unknown")
        task = self.running_tasks.get((index, field))
        if (not task) or task.done() and status == "Active":
            logger.warning(f"Preprocessor {index}.{field} is {status}, but has no running task: {task}")
            return "Unknown"
        return status


@cache
def get_manager():
    return PreprocessorManager()


def start_processors():
    logger.info("Starting preprocessing loops (if needed)")
    manager = get_manager()
    for index in amcat4.index.list_known_indices():
        try:
            instructions = list(amcat4.index.get_instructions(index.id))
        except NotFoundError:
            logger.warning(f"Index {index.id} does not exist!")
            continue
        for instruction in instructions:
            manager.add_preprocessor(index.id, instruction)


async def run_processor_loop(index, instruction: PreprocessingInstruction):
    """
    Main preprocessor loop.
    Calls process_documents to process a batch of documents, until 'done'
    """
    logger.info(f"Preprocessing START for {index}.{instruction.field}")
    get_manager().set_status(index, instruction.field, "Active")
    done = False
    while not done:
        try:
            done = await process_documents(index, instruction)
        except asyncio.CancelledError:
            logger.info(f"Preprocessing CANCEL for {index}.{instruction.field} cancelled")
            get_manager().set_status(index, instruction.field, "Stopped")
            raise
        except RateLimit:
            logger.info(f"Peprocessing RATELIMIT  for {index}.{instruction.field}")
            get_manager().set_status(index, instruction.field, "Paused")
            await asyncio.sleep(PAUSE_ON_RATE_LIMIT_SECONDS)
        except Exception:
            logger.exception(f"Preprocessing ERROR for {index}.{instruction.field}")
            get_manager().set_status(index, instruction.field, "Error")
            return
    get_manager().set_status(index, instruction.field, "Done")
    logger.info(f"Preprocessing DONE for {index}.{instruction.field}")


async def process_documents(index: str, instruction: PreprocessingInstruction, size=100):
    """
    Process a batch of currently to-do documents in the index for this instruction.
    Return value indicates job completion:
    It returns True when it runs out of documents to do, or False if there might be more documents.
    """
    # Refresh index before getting new documents to make sure status updates are reflected
    amcat4.index.refresh_index(index)
    docs = list(get_todo(index, instruction, size=size))
    if not docs:
        return True
    logger.debug(f"Preprocessing for {index}.{instruction.field}: retrieved {len(docs)} docs to process")
    for doc in docs:
        await process_doc(index, instruction, doc)
    return False


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
        logger.exception(f"Error on preprocessing {index}.{instruction.field} doc {doc['_id']}")
        amcat4.index.update_document(index, doc["_id"], {instruction.field: dict(status="error", error=str(e))})
        return
    try:
        response = await AsyncClient().send(req)
        response.raise_for_status()
    except HTTPStatusError as e:
        if e.response.status_code == 503:
            raise RateLimit(e)
        logging.exception(f"Error on preprocessing {index}.{instruction.field} doc {doc['_id']}")
        body = dict(status="error", status_code=e.response.status_code, response=e.response.text)
        amcat4.index.update_document(index, doc["_id"], {instruction.field: body})
        return
    result = dict(instruction.parse_output(response.json()))
    result[instruction.field] = dict(status="done")
    amcat4.index.update_document(index, doc["_id"], result)
