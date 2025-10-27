import logging
from typing import Literal
from amcat4.elastic.connection import elastic_connection
from amcat4.elastic.util import (
    SystemIndexMapping,
    system_index_name,
)
from amcat4.systemdata.versions import VERSIONS, LATEST_VERSION
from pydantic import BaseModel


class InvalidSystemIndex(Exception):
    pass


def create_or_update_systemdata(rm_pending_migrations: bool = True, rm_broken_versions: bool = False) -> int:
    """
    This is the main function. It should be called at startup, and will automatically
    update the system indices mappings and start a migration if needed. This will
    fail if there are pending migrations or if a version is broken (i.e. some indices missing).
    You can override this behaviour by setting the force_rm_* flags to True.

    :param rm_pending_migrations: If True (default), pending migrations will be deleted automatically. This should
                                  be safe, since it should be impossible that these indices have been used yet. but
                                  we still require this flag to make it explicit.
    :param rm_broken_versions: If True, broken versions (with missing indices) will be deleted automatically. This
                               is NOT safe, since these indices might contain important data. So by default this is False.
                               But we should have (todo) a migrate script that can be run manually from the command line.
    :return: The active systemdata version after the operation.
    """

    # Check the current version of the system indices exists
    active_version = active_systemdata_status(LATEST_VERSION, rm_pending_migrations, rm_broken_versions)

    if active_version is None:
        logging.info("No active system index version exists. Creating latest version mappings.")
        # No active system indices version exists, so we don't need to migrate. Just create the mappings.
        create_systemdata_mappings(LATEST_VERSION, migration_pending=False)

    elif active_version == LATEST_VERSION:
        logging.info(f"System index already at version {LATEST_VERSION}. Performing mapping update if needed.")
        update_systemdata_mappings(LATEST_VERSION)

    else:
        logging.info(f"Syst index at version {active_version}, migrating to version {LATEST_VERSION}")
        migrate(active_version, LATEST_VERSION)

    return LATEST_VERSION


def active_systemdata_status(
    latest_version: int, rm_pending_migrations: bool = True, rm_broken_versions: bool = False
) -> int | None:
    """
    Find which systemdata version is currently active, and return its version nr.
    To migrate from this version to the latest version,there cannot be any broken
    versions in between. A version is broken if some of its indices are missing,
    or if some are still pending migration (i.e. have the migration_pending meta flag set).
    The rm_* flags can be used to automatically delete broken versions or pending migrations.

    Indices with pending migrations can safely be deleted, because they cannot have
    been in use yet. This is also a more common problem, which occurs if a migration
    script is stopped or fails halfway. So by default rm_pending_migrations is True.

    Missing indices are trickier. This should only happen if there is a bug or if
    someone manually deleted indices directly in elasticsearch. In this case the
    remaining systemdata might contain important data, so by default
    rm_broken_versions is False.
    """
    for i in range(latest_version, 1, -1):
        status = systemdata_version_status(i)

        if status.broken:
            if status.pending_migrations:
                if rm_pending_migrations:
                    delete_pending_migrations(status.version)
                    status = systemdata_version_status(i)
                else:
                    raise InvalidSystemIndex(
                        f"System index version {i} has pending migrations: {', '.join(status.pending_migrations)}. "
                        "The migrations scripts assume that no data is present in the indices, so either delete "
                        "them, unless you ."
                    )

            if status.missing_indices:
                if rm_broken_versions:
                    delete_systemdata_version(status.version)
                    status = systemdata_version_status(i)
                else:
                    raise InvalidSystemIndex(
                        f"System index version {i} is broken due to missing indices: {', '.join(status.missing_indices)} "
                        "If this happens during development and you are certain these indices do not contain important data, "
                        "you can call the migration script with rm_broken_versions = True. "
                    )

            # recheck status
            if status.broken:
                raise RuntimeError("The system indices version is still broken after trying to fix it.")

        if status.does_not_exist:
            # if the version does not exist (after rm operations), move on to prior versions
            continue
        else:
            return status.version

    return None


def migrate(active_version: int, latest_version: int) -> None:
    for from_version in range(active_version, latest_version):
        to_version = from_version + 1
        migrate_to_version(to_version)


def migrate_to_version(version: int):
    create_systemdata_mappings(version, migration_pending=True)
    VERSIONS[version].migrate()
    set_migration_successfull(version)


def create_systemdata_mappings(version: int, migration_pending: bool) -> None:
    indices: list[SystemIndexMapping] = VERSIONS[version].SYSTEM_INDICES
    for index in indices:
        body = {
            "dynamic": "strict",
            "properties": index.mapping,
        }
        if migration_pending:
            body["_meta"] = {
                "migration_pending": True,
            }
        index = system_index_name(version, index.name)
        elastic_connection().indices.create(index=index, mappings=body)


def update_systemdata_mappings(version: int) -> None:
    indices: list[SystemIndexMapping] = VERSIONS[version].SYSTEM_INDICES
    for index in indices:
        id = system_index_name(version, index.name)
        elastic_connection().indices.put_mapping(index=id, properties=index.mapping)


class SystemIndexVersionStatus(BaseModel):
    version: int
    broken: bool = False  # True if some indices are missing or have pending migrations
    does_not_exist: bool = True  # True if no indices for this version exist
    pending_migrations: list[str] = []  # list of indices with pending migrations
    missing_indices: list[str] = []  # list of indices that are missing


def systemdata_version_status(version: int) -> SystemIndexVersionStatus:
    version_indices: list[SystemIndexMapping] = VERSIONS[version].SYSTEM_INDICES

    status = SystemIndexVersionStatus(version=version)

    for system_index in version_indices:
        index = system_index_name(version, system_index.name)

        index_status = check_index_status(index)

        if index_status == "missing":
            status.missing_indices.append(index)
        else:
            status.does_not_exist = False
            if index_status == "migrating":
                status.pending_migrations.append(index)

    if status.does_not_exist:
        # If no indices exist, none are 'missing'
        status.missing_indices = []

    status.broken = len(status.missing_indices) > 0 or len(status.pending_migrations) > 0

    return status


def delete_pending_migrations(version: int) -> None:
    indices: list[SystemIndexMapping] = VERSIONS[version].SYSTEM_INDICES

    for index in indices:
        index_name = system_index_name(version, index.name)

        mapping = elastic_connection().indices.get_mapping(index=index_name)
        if not mapping:
            raise InvalidSystemIndex(
                f"delete_pending_migrations called for system indices version {version} "
                "but index {index_name} does not exist"
            )

        meta = mapping[index_name]["mappings"].get("_meta", {})
        if meta.get("migration_pending", True):
            elastic_connection().indices.delete(index=index_name)


def delete_systemdata_version(version: int) -> None:
    indices: list[SystemIndexMapping] = VERSIONS[version].SYSTEM_INDICES
    for index in indices:
        index_name = system_index_name(version, index.name)
        elastic_connection().indices.delete(index=index_name, ignore_unavailable=True)


def set_migration_successfull(version) -> None:
    update_meta_body = {"_meta": {"migration_pending": None}}

    for system_index in VERSIONS[version].SYSTEM_INDICES:
        index = system_index_name(version, system_index["name"])
        elastic_connection().indices.put_mapping(index=index, body=update_meta_body)

        # verify, because it's important
        if check_index_status(index) != "ready":
            raise RuntimeError(f"Failed to update migration_pending meta for system index {index}")


def check_migration_flag(index: str) -> bool:
    mapping = elastic_connection().indices.get_mapping(index=index)
    meta = mapping[index]["mappings"].get("_meta", {})
    return meta.get("migration_pending", False)


def check_index_status(index: str) -> Literal["missing", "migrating", "ready"]:
    try:
        mapping = elastic_connection().indices.get_mapping(index=index)
        meta = mapping[index]["mappings"].get("_meta", {})
        if meta.get("migration_pending", False):
            return "migrating"
        else:
            return "ready"
    except Exception:
        return "missing"
