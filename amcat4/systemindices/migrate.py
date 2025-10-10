import logging
from amcat4.elastic_connection import _elastic_connection
from amcat4.systemindices.util import (
    system_index_name,
    SystemIndex,
)
from amcat4.systemindices.versions import v1, v2

VERSIONS = {1: v1, 2: v2}
VERSION = 2


class InvalidSystemIndex(Exception):
    pass


def create_or_update_system_indices() -> None:
    """
    This is the main function. It should be called at startup,
    and will automatically update the system indices mappings
    and start a migration if needed.
    """
    version = VERSION
    indices: list[SystemIndex] = VERSIONS[version].SYSTEM_INDICES

    # Check the current version of the system indices exists
    current_version = current_system_index()

    if current_version is None:
        put_system_indices_mappings(version, indices)

    elif current_version == version:
        logging.info(
            f"System index already at version {version}. Performing mapping update if needed."
        )
        put_system_indices_mappings(version, indices)

    else:
        logging.info(
            f"System index at version {current_version}, migrating to version {version}"
        )
        migrate(current_version, version)


def current_system_index():
    for i in range(VERSION + 1, 1, -1):
        if all_system_indices_exist(i):
            return i
    return None


def migrate(from_version: int, to_version: int) -> None:
    for version in range(from_version, to_version):
        next_version = VERSIONS[version + 1]

        put_system_indices_mappings(version + 1, next_version.indices)

        next_version.migrate()


def put_system_indices_mappings(version: int, indices: list[SystemIndex]) -> None:
    for index in indices:
        index = system_index_name(version, index["name"])
        _elastic_connection().indices.put_mapping(
            index=index, dynamic='strict', properties=index["mapping"]
        )


def all_system_indices_exist(version: int) -> bool:
    """
    Checks whether all system indices for the given version exists,
    and checks the 'migration_successful' flag in the mapping.
    if not, delete any existing system indices of this version and return False.
    """
    system_indices = VERSIONS[version].SYSTEM_INDICES

    broken = False     # If broken, we return false
    exists: list[str] = []   # If broken, delete existing indices
    for system_index in system_indices:
        index = system_index_name(version, system_index["name"])
        mapping = _elastic_connection().indices.get_mapping(
            index=index, ignore_unavailable=True
        )

        if mapping:
            exists.append(index)
            meta = mapping[index]["mappings"].get("_meta", {})
            migration_successfull = meta.get("migration_successfull", False)
            if not migration_successfull:
                broken = True
        else:
            broken = True

    if broken:
        for ix in exists:
            _elastic_connection().indices.delete(index=ix, ignore_unavailable=True )
        return False

    return True


def set_migration_successfull(version) -> None:
    update_meta_body = {
        "mappings": {
            "_meta": {
                "migration_successfull": True
            }
        }
    }

    for system_index in VERSIONS[version].SYSTEM_INDICES:
        index = system_index_name(version, system_index["name"])
        _elastic_connection().indices.put_mapping(index=index, body=update_meta_body)
