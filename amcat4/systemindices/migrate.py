import logging
from amcat4.elastic_connection import _elastic_connection
from amcat4.systemindices.util import (
    system_index_name,
    SystemIndex,
)
from amcat4.systemindices.versions import v1, v2
from pydantic import BaseModel

VERSIONS = {1: v1, 2: v2}
LATEST_VERSION = max(VERSIONS.keys())


class InvalidSystemIndex(Exception):
    pass


class SystemIndexVersionStatus(BaseModel):
    version: int
    uninitialized: bool = True           # has it been created at all?
    pending_migrations: list[str] = []   # list of indices with pending migrations
    missing_indices: list[str] = []      # list of indices that are missing


def create_or_update_system_indices() -> None:
    """
    This is the main function. It should be called at startup,
    and will automatically update the system indices mappings
    and start a migration if needed.
    """
    # Check the current version of the system indices exists
    active_systemindices = active_systemindices_status(force_delete_pending_migrations = True)

    if active_systemindices is None:
        # No active system indices version exists, so we don't need to migrate. Just create the mappings.
        create_or_update_system_indices_mappings(LATEST_VERSION)

    elif active_systemindices.version == LATEST_VERSION:
        logging.info(
            f"System index already at version {LATEST_VERSION}. Performing mapping update if needed."
        )
        create_or_update_system_indices_mappings(LATEST_VERSION)

    else:
        logging.info(
            f"Syst index at version {active_systemindices.version}, migrating to version {LATEST_VERSION}"
        )

        migrate(active_systemindices.version, LATEST_VERSION)


def active_systemindices_status(
    force_delete_pending_migrations: bool = False,
    force_delete_missing_indices: bool = False
) -> SystemIndexVersionStatus | None:
    """

    """
    for i in range(LATEST_VERSION + 1, 1, -1):
        status = system_indices_version_status(i)
        if status.uninitialized:
            continue

        if len(status.missing_indices) > 0:
            if not force_delete_missing_indices:
                raise InvalidSystemIndex(
                    f"System index version {i} exists but has missing indices: {', '.join(status.missing_indices)} "
                    "This shouldnt ever happen without manually interacting with elastic directly. "
                    "If this happens during development and you are certain these indices to not contain important data, "
                    "you can call migration manually with force_delete_missing_indices = True. "
                )

            delete_systemindices_version(status.version)
            if system_indices_version_status(i).uninitialized:
                continue
            else:
                raise RuntimeError("The system indices version still exists after trying to delete it.")

        if len(status.pending_migrations) > 0:
            if not force_delete_pending_migrations:
                raise InvalidSystemIndex(
                    f"System index version {i} has pending migrations: {', '.join(status.pending_migrations)}. "
                    "The migrations scripts assume that no data is present in the indices, so either delete "
                    "the indices or complete the migrations manually (see documentation)."
                )

            delete_pending_migrations(status.version)
            if system_indices_version_status(i).uninitialized:
                continue
            else:
                raise RuntimeError("The system indices version still has pending migrations.")

        return status
    return None


def migrate(active_version: int, latest_version: int) -> None:
    for from_version in range(active_version, latest_version):
        to_version = from_version + 1
        migrate_to_version(to_version)


def migrate_to_version(version: int):
    create_or_update_system_indices_mappings(version, migration_pending=True)
    VERSIONS[version].migrate()


def create_or_update_system_indices_mappings(version: int, migration_pending: bool = False) -> None:
    indices = VERSIONS[version].SYSTEM_INDICES
    for index in indices:
        body = {
            "dynamic": 'strict',
            "properties": index.mapping,
        }
        if migration_pending:
            body['_meta'] = {
                "migration_pending": True,
            }

        index = system_index_name(version, index.name])
        _elastic_connection().indices.put_mapping(index=index, body=body)





def system_indices_version_status(version: int) -> SystemIndexVersionStatus:
    version_indices = VERSIONS[version].SYSTEM_INDICES

    status = SystemIndexVersionStatus(version=version)

    for system_index in version_indices:
        index = system_index_name(version, system_index["name"])

        try:
            mapping = _elastic_connection().indices.get_mapping(index=index)
            # If at least one index exists, it has been created at some point
            status.uninitialized = False

            meta = mapping[index]["mappings"].get("_meta", {})
            if not meta.get("migration_pending", True):
                status.pending_migrations.append(index)

        except Exception:
            status.missing_indices.append(index)



    return status


def delete_pending_migrations(version: int) -> None:
    indices = VERSIONS[version].SYSTEM_INDICES

    for index in indices:
        index_name = system_index_name(version, index.name)

        mapping = _elastic_connection().indices.get_mapping(index=index_name)
        if not mapping:
            raise InvalidSystemIndex(f"delete_pending_migrations called for system indices version {version} "
                                      "but index {index_name} does not exist")

        meta = mapping[index]["mappings"].get("_meta", {})
        if meta.get("migration_pending", True):
            _elastic_connection().indices.delete(index=index_name)


def delete_systemindices_version(version: int) -> None:
    indices = VERSIONS[version].SYSTEM_INDICES
    for index in indices:
        index_name = system_index_name(version, index.name)
        _elastic_connection().indices.delete(index=index_name, ignore_unavailable=True )


def set_migration_successfull(version) -> None:
    update_meta_body = {"_meta": {"migration_pending": None}}

    for system_index in VERSIONS[version].SYSTEM_INDICES:
        index = system_index_name(version, system_index["name"])
        _elastic_connection().indices.put_mapping(index=index, body=update_meta_body)
