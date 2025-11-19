"""
Sets up the connection to the Elastic server.
In most cases you should use the es() function from elastic.py instead,
because this also sets up the system index. Only use _elastic_connection()
directly in the system_index folder to avoid circular imports.
"""

import logging

from elasticsearch import AsyncElasticsearch

from amcat4.config import get_settings


class ESConnectionHolder:
    active: AsyncElasticsearch | None = None


ES_CONNECTION = ESConnectionHolder()


async def elastic_connection() -> AsyncElasticsearch:
    """
    Get the elasticsearch connection.
    This function is cached, so multiple calls return the same connection.
    """
    if ES_CONNECTION.active is None:
        ES_CONNECTION.active = await setup_elastic()
    return ES_CONNECTION.active


async def close_elastic() -> None:
    if ES_CONNECTION.active is not None:
        await ES_CONNECTION.active.close()


async def setup_elastic():
    """
    Check whether we can connect with elastic
    """
    settings = get_settings()
    logging.debug(
        f"Connecting with elasticsearch at {settings.elastic_host}, password? {'yes' if settings.elastic_password else 'no'} "
    )
    elastic = await connect_elastic()
    if not await elastic.ping():
        raise ConnectionError(f"Cannot connect to elasticsearch server {settings.elastic_host}")
    return elastic


async def connect_elastic() -> AsyncElasticsearch:
    """
    Connect to the elastic server using the system settings
    """
    settings = get_settings()
    if settings.elastic_password:
        host = settings.elastic_host
        if settings.elastic_verify_ssl is None:
            verify_certs = "localhost" in (host or "")
        else:
            verify_certs = settings.elastic_verify_ssl

        return AsyncElasticsearch(
            host,
            basic_auth=("elastic", settings.elastic_password),
            verify_certs=verify_certs,
        )
    else:
        return AsyncElasticsearch(settings.elastic_host or None)
