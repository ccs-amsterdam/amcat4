import asyncio
from time import sleep
from httpx import AsyncClient
from requests import Session
from amcat4.elastic import es
from amcat4.index import refresh_index, update_document
from amcat4.preprocessing.instruction import PreprocessingInstruction
from amcat4.preprocessing.task import get_task


async def run_preprocessors():
    pass


async def process_documents(index: str, instruction: PreprocessingInstruction, size=100):
    """
    Process all currently to-do documents in the index for this instruction.
    Returns when it runs out of documents to do
    """
    # Q: it it better to repeat a simple "get n todo docs", or to iteratively scroll past all todo items?
    while True:
        docs = list(get_todo(index, instruction, size=size))
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


async def process_doc(index: str, instruction: PreprocessingInstruction, doc: dict):
    req = instruction.build_request(doc)
    response = await AsyncClient().send(req)
    response.raise_for_status()
    result = dict(instruction.parse_output(response.json()))
    result[instruction.field] = dict(status="done")
    update_document(index, doc["_id"], result)
