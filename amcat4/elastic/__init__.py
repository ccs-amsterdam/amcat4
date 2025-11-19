"""
Connection between AmCAT4 and the elasticsearch backend

This function should be used throughout the codebase to get the Elasticsearch
connection, because it also ensures that the system indices are created and up to date.

Note that we also run the create_or_update_systemdata in the FastAPI startup script,
so that FastAPI doesn't launch if the system indices cannot be created or updated.
The reason we also include it here is that scripts or other code that uses AmCAT4
without FastAPI still needs to ensure that the system indices are present.

!! Maybe we should refactor this, and explicitly call create_or_update_systemdata
in scripts that need it, instead of doing it implicitly here.
"""

from async_lru import alru_cache
from elasticsearch import AsyncElasticsearch

from amcat4.elastic.connection import elastic_connection
from amcat4.systemdata.manage import create_or_update_systemdata


@alru_cache(maxsize=1)
async def es() -> AsyncElasticsearch:
    await create_or_update_systemdata()
    return await elastic_connection()
