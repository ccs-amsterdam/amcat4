"""
Connection between AmCAT4 and the elasticsearch backend

Some things to note:
- See config.py for global settings, including elastic host and system index name
- The elasticsearch backend should contain a system index, which will be created if needed
- The system index contains a 'document' for each used index containing:
  {auth: [{email: role}], guest_role: role}

"""

import functools
import logging
from typing import Optional

from elasticsearch import Elasticsearch, NotFoundError

from amcat4.config import get_settings

SYSTEM_INDEX_VERSION = 2

SYSTEM_MAPPING = {
    "name": {"type": "text"},
    "description": {"type": "text"},
    "roles": {"type": "nested"},
    "requests": {"type": "nested"},
    "summary_field": {"type": "keyword"},
    "guest_role": {"type": "keyword"},
    "folder": {"type": "keyword"},
    "image_url": {"type": "keyword"},
    "branding": {"type": "object"},
    "external_url": {"type": "keyword"},
}


class CannotConnectElastic(Exception):
    pass


@functools.lru_cache()
def es() -> Elasticsearch:
    try:
        return _setup_elastic()
    except ValueError as e:
        raise ValueError(f"Cannot connect to elastic {get_settings().elastic_host!r}: {e}")


def connect_elastic() -> Elasticsearch:
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


def get_system_version(elastic=None) -> Optional[int]:
    """
    Get the elastic system index version
    """
    # WvA: I don't like this 'circular' import. Should probably reorganize the elastic and index modules
    from amcat4.index import GLOBAL_ROLES

    settings = get_settings()
    if elastic is None:
        elastic = es()
    try:
        r = elastic.get(index=settings.system_index, id=GLOBAL_ROLES, source_includes="version")
    except NotFoundError:
        return None
    return r["_source"].get("version")


def _setup_elastic():
    """
    Check whether we can connect with elastic
    """
    # WvA: I don't like this 'circular' import. Should probably reorganize the elastic and index modules
    from amcat4.index import GLOBAL_ROLES

    settings = get_settings()
    logging.debug(
        f"Connecting with elasticsearch at {settings.elastic_host}, "
        f"password? {'yes' if settings.elastic_password else 'no'} "
    )
    elastic = connect_elastic()
    if not elastic.ping():
        raise CannotConnectElastic(f"Cannot connect to elasticsearch server {settings.elastic_host}")
    if elastic.indices.exists(index=settings.system_index):
        # Check index format version
        if version := get_system_version(elastic) is None:
            raise CannotConnectElastic(
                f"System index {settings.elastic_host}::{settings.system_index} is corrupted or uses an "
                f"old format. Please repair or migrate before continuing"
            )
        if version < SYSTEM_INDEX_VERSION:
            # Try to set mapping of each field, warn if not possible
            for field, fieldtype in SYSTEM_MAPPING.items():
                try:
                    elastic.indices.put_mapping(
                        index=settings.system_index,
                        properties={field: fieldtype},
                    )
                except Exception as e:
                    logging.warning(e)

    else:
        logging.info(f"Creating amcat4 system index: {settings.system_index}")
        elastic.indices.create(index=settings.system_index, mappings={"properties": SYSTEM_MAPPING})
        elastic.index(
            index=settings.system_index,
            id=GLOBAL_ROLES,
            document=dict(version=SYSTEM_INDEX_VERSION, roles=[]),
        )
    return elastic


def ping():
    """
    Can we reach this elasticsearch server
    """
    try:
        return es().ping()
    except CannotConnectElastic as e:
        logging.error(e)
        return False
