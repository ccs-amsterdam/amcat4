
"""
Sets up the connection to the Elastic server.
In most cases you should use the es() function from elastic.py instead,
because this also sets up the system index. Only use _elastic_connection()
directly in the system_index folder to avoid circular imports.
"""
import functools
import logging
from elasticsearch import Elasticsearch
from amcat4.config import get_settings


class CannotConnectElastic(Exception):
    pass


@functools.lru_cache()
def _elastic_connection() -> Elasticsearch:
    try:
        return _setup_elastic()
    except Exception as e:
        raise Exception(f"Cannot connect to elastic {get_settings().elastic_host!r}: {e}")


def _connect_elastic() -> Elasticsearch:
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

        return Elasticsearch(
            host,
            basic_auth=("elastic", settings.elastic_password),
            verify_certs=verify_certs,
        )
    else:
        return Elasticsearch(settings.elastic_host or None)


def _setup_elastic():
    """
    Check whether we can connect with elastic
    """
    settings = get_settings()
    logging.debug(
        f"Connecting with elasticsearch at {settings.elastic_host}, "
        f"password? {'yes' if settings.elastic_password else 'no'} "
    )
    elastic = _connect_elastic()
    if not elastic.ping():
        raise CannotConnectElastic(f"Cannot connect to elasticsearch server {settings.elastic_host}")
    return elastic
