import amcat4.system_index.system_index_v1 as system_index_v1
import amcat4.system_index.system_index_v2 as system_index_v2
from amcat4.system_index.util import create_or_refresh_system_index, current_system_index, safe_write_to_system_index
import logging

# HERE SELECT LATEST VERSION OF SYSTEM INDEX
system_index = system_index_v1


class InvalidSystemIndex(Exception):
    pass


def migrate():
    spec = system_index.SPEC
    current = current_system_index(spec.version)
    if current == spec.version:
        logging.info(f"System index already at version {spec.version}")
        return
    if current is None:
        logging.info("No existing system index found, creating new one")
        create_or_refresh_system_index(spec)
        return

    for version in range(current, spec.version):
        if version == 1:
            system_index_v2.migrate()
        elif version == 2:
            # future migration path
            pass
        else:
            raise InvalidSystemIndex(f"No migration path for system index version {version}")


def setup_system_index() -> None:
    create_or_refresh_system_index(system_index.SPEC)


def insert_to_system_index(path: str, doc: dict | list[dict]) -> None:
    """
    Insert a document or list of documents into the system index at the given path.
    This will validate the document(s) against the system index specification before inserting.
    """
    safe_write_to_system_index(system_index.SPEC, path, doc, op_type="index")


def update_system_index(path: str, doc: dict | list[dict]) -> None:
    """
    Update a document or list of documents in the system index at the given path.
    This will validate the document(s) against the system index specification before updating.
    """
    safe_write_to_system_index(system_index.SPEC, path, doc, op_type="update")
