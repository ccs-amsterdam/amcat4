"""
Connection between AmCAT4 and the elasticsearch backend

Some things to note:
- See config.py for global settings, including elastic host and system index name
- The elasticsearch backend should contain a system index, which will be created if needed
- The system index contains a 'document' for each used index containing:
  {auth: [{email: role}], guest_role: role}

"""
import functools
from elasticsearch import Elasticsearch

from amcat4.config import get_settings
from amcat4.elastic_connection import _elastic_connection
from amcat4.system_index.system_index import setup_system_index


@functools.lru_cache()
def es() -> Elasticsearch:
    setup_system_index()
    return _elastic_connection()
