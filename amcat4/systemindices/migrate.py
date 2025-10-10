
import logging
import importlib
from amcat4.elastic_connection import _elastic_connection
from amcat4.systemindices.util import system_index_prefix, system_index_name, SystemIndex

VERSION = 2


class InvalidSystemIndex(Exception):
    pass


def create_or_update_system_indices(version: int) -> None:
    """
    This is the main function.
    Create or refresh the system index and its mappings.
    If the index already exists, update its mappings.
    If the index does not exist, create it.
    If an older version of the index exists, raise an error and ask the user to migrate.
    """
    v = importlib.import_module(f"amcat4.systemindices.versions.v{version}")
    indices: list[SystemIndex] = v.SYSTEM_INDICES

    # Check the current version of the system indices exists
    current_version = current_system_index()

    if current_version is None:
        put_system_index_mappings(version, indices)

    elif current_version == version:
        logging.info(f"System index already at version {version}. Performing mapping update if needed.")
        put_system_index_mappings(version, indices)

    else:
        logging.info(f"System index at version {current_version}, migrating to version {version}")
        migrate(current_version, version)


def current_system_index():
    for i in range(VERSION + 1, 1, -1):
        prefix = system_index_prefix(i)
        if _elastic_connection().indices.exists(index=f"{prefix}*"):
            return i
    return None


def migrate(from_version: int, to_version: int) -> None:
    for version in range(from_version, to_version):
        next_version = importlib.import_module(f"amcat4.systemindices.versions.v{version+1}")
        next_version.migrate()


def put_system_index_mappings(version: int, indices: list[SystemIndex]) -> None:
    for system_index in indices:
        index = system_index_name(version, system_index["name"])
        _elastic_connection().indices.put_mapping(index=index, properties=system_index["mapping"])




# def safe_write_to_system_index(spec: SystemIndexSpec, path: str, docs: list[dict] | dict, op_type: Literal["index", "update"] = "index", refresh: bool = True) -> None:
#     """
#     Safely write one or more documents to the system index, validating them first.
#     If op_type is "index", the document will be created or replaced.
#     If op_type is "update", the document will be updated (and must already exist).
#     """
#     index = get_system_index_name(spec.version, path)
#     docs = docs if isinstance(docs, list) else [docs]

#     actions = []
#     partial = op_type == "update"

#     for doc in docs:
#         valid_doc = validate_system_index_input(spec, path, doc, partial=partial)
#         id = valid_doc.pop("id", None)
#         if not id:
#             raise ValueError("Document must have an 'id' field")

#         actions.append({
#             "_index": index,
#             "_id": id,
#             "_op_type": "index",
#             "doc": valid_doc
#         })

#         try:
#             elasticsearch.helpers.bulk(
#                 _elastic_connection(),
#                 actions,
#                 stats_only=False,
#             )
#         except elasticsearch.helpers.BulkIndexError as e:
#             logging.error("Error on updating system index: " + json.dumps(e.errors, indent=2, default=str))

#     if refresh:
#         refresh_index(spec, path)


# def refresh_index(spec: SystemIndexSpec, path: str) -> None:
#     index = get_system_index_name(spec.version, path)
#     _elastic_connection().indices.refresh(index=index)
