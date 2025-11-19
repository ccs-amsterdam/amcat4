import logging
from typing import Literal

from elasticsearch import BadRequestError
from pydantic import BaseModel

from amcat4.elastic.connection import elastic_connection
from amcat4.elastic.util import (
    SystemIndexMapping,
    system_index_name,
)
from amcat4.systemdata.versions import LATEST_VERSION, VERSIONS


class InvalidSystemIndex(Exception):
    pass


async def create_or_update_systemdata(rm_pending_migrations: bool = True) -> int:
    """
    This is the main function. It should be called at startup, and will automatically
    update the system indices mappings and start a migration if needed. This will
    fail if there are pending migrations or if a version is broken (i.e. some indices missing).

    :param rm_pending_migrations: If True (default), pending migrations will be deleted automatically. This should
                                  be safe, since it should be impossible that these indices have been used yet. but
                                  we still require this flag to make it explicit.
    :return: The active systemdata version after the operation.
    """

    # Check the current version of the system indices exists
    active_version = await active_systemdata_status(LATEST_VERSION, rm_pending_migrations)

    if active_version is None:
        logging.info("No active system index version exists. Creating latest version mappings.")
        # No active system indices version exists, so we don't need to migrate. Just create the mappings.
        await create_systemdata_mappings(LATEST_VERSION, migration_pending=False)

    elif active_version == LATEST_VERSION:
        logging.info(f"System index already at version {LATEST_VERSION}. Performing mapping update if needed.")
        try:
            await update_systemdata_mappings(LATEST_VERSION)
        except BadRequestError as e:
            raise InvalidSystemIndex(
                f"Failed to update system index mappings for version {LATEST_VERSION}. "
                f"This indicates that the existing mappings are incompatible with the mappings in v{LATEST_VERSION}.py. "
                "This shouldn't happen, and indicates someone changed the system index mappings manually. "
                "This is only ok if you are working on a new system index version, in which case you can "
                "use the dangerously_destroy_systemdata function in the manage module to remove this version. "
            ) from e

    else:
        logging.info(f"Syst index at version {active_version}, migrating to version {LATEST_VERSION}")
        await migrate(active_version, LATEST_VERSION)

    return LATEST_VERSION


async def active_systemdata_status(latest_version: int, rm_pending_migrations: bool = True) -> int | None:
    """
    Find which systemdata version is currently active, and return its version nr.
    To migrate from this version to the latest version,there cannot be any broken
    versions in between. A version is broken if some of its indices are missing,
    or if some are still pending migration (i.e. have the migration_pending meta flag set).

    Indices with pending migrations can safely be deleted, because they cannot have
    been in use yet. This is also a more common problem, which occurs if a migration
    script is stopped or fails halfway. So by default pending migrations are deleted
    automatically (rm_pending_migrations is True).

    Missing indices are trickier. This should only happen if there is a bug or if
    someone manually deleted indices directly in elasticsearch. In this case the
    remaining systemdata might contain important data. You either need to fix it manually,
    or use the dangerously_destroy_systemdata function in the manage module to remove
    this version (obviously, you will lose all data in the system indices of this version).
    """
    for i in range(latest_version, 1, -1):
        status = await systemdata_version_status(i)

        if status.broken:
            if status.pending_migrations:
                if rm_pending_migrations:
                    await delete_pending_migrations(status.version)
                    status = await systemdata_version_status(i)
                else:
                    raise InvalidSystemIndex(
                        f"System index version {i} has pending migrations: {', '.join(status.pending_migrations)}. "
                        "The migrations scripts assume that no data is present in the indices, so either delete "
                        "them or finish the migrations manually. "
                    )

            if status.incorrect_mapping or status.missing_indices:
                raise InvalidSystemIndex(
                    f"System index version {i} is broken due to missing indices. "
                    "This shouldn't happen, and indicates someone deleted indices manually. "
                    "This is only ok if you are working on a new system index version, in which case you can "
                    "use the dangerously_destroy_systemdata function in the manage module to remove this version. "
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


async def migrate(active_version: int, latest_version: int) -> None:
    for from_version in range(active_version, latest_version):
        to_version = from_version + 1
        await migrate_to_version(to_version)


async def migrate_to_version(version: int):
    await create_systemdata_mappings(version, migration_pending=True)
    await VERSIONS[version].migrate()
    await set_migration_successfull(version)


async def create_systemdata_mappings(version: int, migration_pending: bool) -> None:
    indices: list[SystemIndexMapping] = VERSIONS[version].SYSTEM_INDICES
    elastic = await elastic_connection()
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
        await elastic.indices.create(index=index, mappings=body)


async def update_systemdata_mappings(version: int) -> None:
    indices: list[SystemIndexMapping] = VERSIONS[version].SYSTEM_INDICES
    elastic = await elastic_connection()
    for index in indices:
        id = system_index_name(version, index.name)
        await elastic.indices.put_mapping(index=id, properties=index.mapping)


class SystemIndexVersionStatus(BaseModel):
    version: int
    broken: bool = False  # True if some indices are missing or have pending migrations
    does_not_exist: bool = True  # True if no indices for this version exist
    incorrect_mapping: bool = False  # True if some indices have incorrect mapping
    pending_migrations: list[str] = []  # list of indices with pending migrations
    missing_indices: list[str] = []  # list of indices that are missing


async def systemdata_version_status(version: int) -> SystemIndexVersionStatus:
    version_indices: list[SystemIndexMapping] = VERSIONS[version].SYSTEM_INDICES

    status = SystemIndexVersionStatus(version=version)

    for system_index in version_indices:
        index = system_index_name(version, system_index.name)

        index_status = await check_index_status(index)

        if index_status == "missing":
            status.missing_indices.append(index)
        else:
            status.does_not_exist = False
            if index_status == "migrating":
                status.pending_migrations.append(index)

    if status.does_not_exist:
        # If no indices exist, none are 'missing'
        status.missing_indices = []

    ## check if missing indices or pending migrations
    status.broken = len(status.missing_indices) > 0 or len(status.pending_migrations) > 0

    return status


async def delete_pending_migrations(version: int) -> None:
    indices: list[SystemIndexMapping] = VERSIONS[version].SYSTEM_INDICES
    elastic = await elastic_connection()
    for index in indices:
        index_name = system_index_name(version, index.name)

        mapping = await elastic.indices.get_mapping(index=index_name)
        if not mapping:
            raise InvalidSystemIndex(
                f"delete_pending_migrations called for system indices version {version} "
                "but index {index_name} does not exist"
            )

        meta = mapping[index_name]["mappings"].get("_meta", {})
        if meta.get("migration_pending", True):
            await elastic.indices.delete(index=index_name)


async def delete_systemdata_version(version: int) -> None:
    indices: list[SystemIndexMapping] = VERSIONS[version].SYSTEM_INDICES
    elastic = await elastic_connection()
    for index in indices:
        index_name = system_index_name(version, index.name)
        await elastic.indices.delete(index=index_name, ignore_unavailable=True)


async def set_migration_successfull(version) -> None:
    update_meta_body = {"_meta": {"migration_pending": None}}
    elastic = await elastic_connection()
    for system_index in VERSIONS[version].SYSTEM_INDICES:
        index = system_index_name(version, system_index["name"])
        await elastic.indices.put_mapping(index=index, body=update_meta_body)

        # verify, because it's important
        if await check_index_status(index) != "ready":
            raise RuntimeError(f"Failed to update migration_pending meta for system index {index}")


async def check_migration_flag(index: str) -> bool:
    elastic = await elastic_connection()
    mapping = await elastic.indices.get_mapping(index=index)
    meta = mapping[index]["mappings"].get("_meta", {})
    return meta.get("migration_pending", False)


async def check_index_status(index: str) -> Literal["missing", "migrating", "ready"]:
    try:
        elastic = await elastic_connection()
        mapping = await elastic.indices.get_mapping(index=index)
        meta = mapping[index]["mappings"].get("_meta", {})
        if meta.get("migration_pending", False):
            return "migrating"
        else:
            return "ready"
    except Exception:
        return "missing"
