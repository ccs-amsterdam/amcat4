from amcat4.systemdata.versions import v1, v2
from amcat4.systemdata.versions.v2 import (
    apikeys_index_name,
    fields_index_id,
    fields_index_name,
    objectstorage_index_id,
    objectstorage_index_name,
    requests_index_id,
    requests_index_name,
    roles_index_id,
    roles_index_name,
    settings_index_id,
    settings_index_name,
)

__all__ = [
    "apikeys_index_name",
    "fields_index_id",
    "fields_index_name",
    "objectstorage_index_id",
    "objectstorage_index_name",
    "requests_index_id",
    "requests_index_name",
    "roles_index_id",
    "roles_index_name",
    "settings_index_id",
    "settings_index_name",
]

VERSIONS = {1: v1, 2: v2}
LATEST_VERSION = max(VERSIONS.keys())
