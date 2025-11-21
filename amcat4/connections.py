from contextlib import asynccontextmanager
from typing import AsyncGenerator

from elasticsearch import AsyncElasticsearch
from types_aiobotocore_s3.client import S3Client

from amcat4.elastic.connection import close_elastic, start_elastic
from amcat4.objectstorage.s3client import close_s3_session, start_s3_client


class AmcatConnections:
    s3_client: S3Client | None
    elastic: AsyncElasticsearch

    def __init__(self, s3_client: S3Client | None, elastic: AsyncElasticsearch):
        self.s3_client = s3_client
        self.elastic = elastic


async def start_amcat_connections() -> AmcatConnections:
    s3_client = await start_s3_client()
    elastic = await start_elastic()
    return AmcatConnections(s3_client=s3_client, elastic=elastic)


async def close_amcat_connections():
    await close_s3_session()
    await close_elastic()


@asynccontextmanager
async def amcat_connections() -> AsyncGenerator[AmcatConnections, None]:
    try:
        yield await start_amcat_connections()
    finally:
        await close_amcat_connections()
