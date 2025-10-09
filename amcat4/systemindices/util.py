
import logging
import json
import elasticsearch.helpers
from pydantic import BaseModel
from amcat4.config import get_settings
from typing import Type, Literal
from amcat4.elastic_connection import _elastic_connection
from amcat4.system_index.mapping import SI_ElasticMapping


class InvalidSystemIndex(Exception):
    pass


class Table(BaseModel):
    path: str
    es_mapping: SI_ElasticMapping



def get_system_index_name(version: int, table: str | None = None):
    index = get_settings().system_index
    if version > 1:
        index = f"{index}_V{version}"
    if table and table != "":
        index = f"{index}_{table}"
    return index


def current_system_index(max_version: int):
    for i in range(max_version + 1, 1, -1):
        index_name = get_system_index_name(i)
        if _elastic_connection().indices.exists(index=index_name):
            return i
    return None


def create_or_refresh_system_index(spec: SystemIndexSpec) -> None:
    """
    Create or refresh the system index and its mappings.
    If the index already exists, update its mappings.
    If the index does not exist, create it.
    If an older version of the index exists, raise an error and ask the user to migrate.
    """
    try:
        for table in spec.tables:
            index = get_system_index_name(spec.version, table.path)
            exists = _elastic_connection().indices.exists(index=index)

            if exists:
                for field, fieldtype in table.es_mapping.items():
                    try:
                        _elastic_connection().indices.put_mapping(index=index, properties={field: fieldtype})
                    except Exception as e:
                        logging.warning(e)
            else:
                current_version = current_system_index(spec.version)
                if current_version is not None and current_version < spec.version:
                    raise InvalidSystemIndex(
                        f"You have an older version of the system index ({current_version} < {spec.version}). "
                        f"Please migrate before continuing"
                    )
                else:
                    logging.info(f"Creating new system index: {index}")
                    _elastic_connection().indices.create(index=index, mappings={"properties": table.es_mapping})

    except Exception as e:
        logging.warning(e)




def safe_write_to_system_index(spec: SystemIndexSpec, path: str, docs: list[dict] | dict, op_type: Literal["index", "update"] = "index", refresh: bool = True) -> None:
    """
    Safely write one or more documents to the system index, validating them first.
    If op_type is "index", the document will be created or replaced.
    If op_type is "update", the document will be updated (and must already exist).
    """
    index = get_system_index_name(spec.version, path)
    docs = docs if isinstance(docs, list) else [docs]

    actions = []
    partial = op_type == "update"

    for doc in docs:
        valid_doc = validate_system_index_input(spec, path, doc, partial=partial)
        id = valid_doc.pop("id", None)
        if not id:
            raise ValueError("Document must have an 'id' field")

        actions.append({
            "_index": index,
            "_id": id,
            "_op_type": "index",
            "doc": valid_doc
        })

        try:
            elasticsearch.helpers.bulk(
                _elastic_connection(),
                actions,
                stats_only=False,
            )
        except elasticsearch.helpers.BulkIndexError as e:
            logging.error("Error on updating system index: " + json.dumps(e.errors, indent=2, default=str))

    if refresh:
        refresh_index(spec, path)


def refresh_index(spec: SystemIndexSpec, path: str) -> None:
    index = get_system_index_name(spec.version, path)
    _elastic_connection().indices.refresh(index=index)


SINGLE_DOC_INDEX_ID = "_single_doc_index"
