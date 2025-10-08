from amcat4.system_index import SPEC
from amcat4.system_index.migrations import v1_to_v2
from amcat4.system_index.util import create_or_refresh_system_index, current_system_index, safe_write_to_system_index
import logging

class InvalidSystemIndex(Exception):
    pass


def migrate():
    current = current_system_index(SPEC.version)
    if current == SPEC.version:
        logging.info(f"System index already at version {SPEC.version}")
        return
    if current is None:
        logging.info("No existing system index found, creating new one")
        create_or_refresh_system_index(SPEC)
        return

    for version in range(current, SPEC.version):
        if version == 1:
            v1_to_v2.migrate()
        elif version == 2:
            # future migration path
            pass
        else:
            raise InvalidSystemIndex(f"No migration path for system index version {version}")
