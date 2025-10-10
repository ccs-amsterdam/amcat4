from amcat4.config import get_settings
from pydantic import BaseModel
from amcat4.elastic_connection import _elastic_connection
from amcat4.elastic_mapping import ElasticMappingProperties


class SystemIndex(BaseModel):
    name: str
    mapping: ElasticMappingProperties
    migrate: callable[[str], None] | None


def system_index_prefix(version: int, migration: bool = False):
    """
    Get the prefix for the system index, based on the version.
    If migration is True, the prefix for the (temporary) migration index is returned.
    """
    index = get_settings().system_index
    if migration:
        index = f"{index}_migrating"
    if version > 1:
        index = f"{index}_V{version}"
    return index


def system_index_name(version: int, path: str, migration: bool = False) -> str:
    """
    Get the full name for the system index, based on the version and path.
    If migration is True, the name for the (temporary) migration index is returned.
    """
    prefix = system_index_prefix(version, migration)
    return f"{prefix}_{path}"


def create_index_alias(source_index: str, target_alias: str):
    """
    Creates an atomic alias, logically "moving" the index by making the
    target_alias point to the source_index. The source index is NOT deleted.
    """

    actions = {
        "actions": [
            {"add": {"index": source_index, "alias": target_alias}}
        ]
    }

    _elastic_connection().indices.update_aliases(body=actions)


# def delete_index_alias(alias: str) -> bool:
#     """
#     Deletes an index alias.
#     """

#     actions = {
#         "actions": [
#             {"remove": {"index": "*", "alias": alias}}
#         ]
#     }
#     return _elastic_connection().indices.update_aliases(body=actions)


# def delete_system_indices(version: int) -> None:
#     """
#     Deletes all system indices of the given version.
#     """
#     ...
