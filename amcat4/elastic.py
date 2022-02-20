import hashlib
import json
import logging
from typing import Mapping, List, Optional

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

_ES: Optional[Elasticsearch] = None
SYS_INDEX = "amcat4system"
SYS_MAPPING = "sys"
REQUIRED_FIELDS = ["title", "date", "text"]
HASH_FIELDS = REQUIRED_FIELDS + ["url"]
DEFAULT_QUERY_FIELDS = HASH_FIELDS

ES_MAPPINGS = {
   'long': {"type": "long"},
   'date': {"type": "date", "format": "strict_date_optional_time"},
   'double': {"type": "double"},
   'keyword': {"type": "keyword"},
   'url': {"type": "keyword", "meta": {"amcat4_type": "url"}},
   'tag': {"type": "keyword", "meta": {"amcat4_type": "tag"}},
   'text': {"type": "text"},
   'object': {"type": "object"},
   'geo_point': {"type": "geo_point"}
   }


def es() -> Elasticsearch:
    if _ES is None:
        raise Exception("Elasticsearch not setup yet")
    return _ES


def setup_elastic(*hosts):
    """
    Check whether we can connect with elastic
    """
    global _ES
    logging.debug("Connecting with elasticsearch at {}".format(hosts or "(default: localhost:9200)"))
    _ES = Elasticsearch(hosts or None)
    if not _ES.ping():
        raise Exception(f"Cannot connect to elasticsearch server {hosts}")
    if not _ES.indices.exists(index=SYS_INDEX):
        logging.info(f"Creating amcat4 system index: {SYS_INDEX}")
        _ES.indices.create(index=SYS_INDEX)


def _list_indices(exclude_system_index=True) -> List[str]:
    """
    List all indices on the connected elastic cluster.
    You should probably use the methods in amcat4.index rather than this.
    """
    result = es().indices.get(index="*")
    return [x for x in result.keys() if not (exclude_system_index and x == SYS_INDEX)]


def _create_index(name: str) -> None:
    """
    Create a new index
    You should probably use the methods in amcat4.index rather than this.
    """
    fields = {'text': ES_MAPPINGS['text'],
              'title': ES_MAPPINGS['text'],
              'date': ES_MAPPINGS['date'],
              'url': ES_MAPPINGS['url']}
    es().indices.create(index=name, mappings={'properties': fields})


def _delete_index(name: str, ignore_missing=False) -> None:
    """
    Delete an index
    You should probably use the methods in amcat4.index rather than this.
    :param name: The name of the new index (without prefix)
    :param ignore_missing: If True, do not throw exception if index does not exist
    """
    es().indices.delete(index=name, ignore=([404] if ignore_missing else []))


def _get_hash(document):
    """
    Get the hash for a document
    """
    hash_dict = {key: document.get(key) for key in HASH_FIELDS}
    hash_str = json.dumps(hash_dict, sort_keys=True, ensure_ascii=True).encode('ascii')
    m = hashlib.sha224()
    m.update(hash_str)
    return m.hexdigest()


def _get_es_actions(index, documents):
    """
    Create the Elasticsearch bulk actions from article dicts.
    If you provide a list to ID_SEQ_LIST, the hashes are copied there
    """
    for document in documents:
        for f in REQUIRED_FIELDS:
            if f not in document:
                raise ValueError("Field {f!r} not present in document {document}".format(**locals()))
        if '_id' not in document:
            document['_id'] = _get_hash(document)
        yield {
            "_index": index,
            **document
        }


def upload_documents(index: str, documents, columns: Mapping[str, str] = None) -> List[str]:
    """
    Upload documents to this index

    :param index: The name of the index (without prefix)
    :param documents: A sequence of article dictionaries
    :param columns: A mapping of field:type for column types
    :return: the list of document ids
    """
    if columns:
        set_columns(index, columns)

    actions = list(_get_es_actions(index, documents))
    bulk(es(), actions)
    return [action['_id'] for action in actions]


def set_columns(index: str, columns: Mapping[str, str]):
    """
    Update the column types for this index

    :param index: The name of the index (without prefix)
    :param columns: A mapping of field:type for column types
    """
    mapping = {field: ES_MAPPINGS[type_] for (field, type_) in columns.items()}
    es().indices.put_mapping(index=index, body=dict(properties=mapping))


def get_document(index: str, doc_id: str, **kargs) -> dict:
    """
    Get a single document from this index

    :param index: The name of the index
    :param doc_id: The document id (hash)
    :return: the source dict of the document
    """
    return es().get(index=index, id=doc_id, **kargs)['_source']


def update_document(index: str, doc_id: str, fields: dict):
    """
    Update a single document


    :param index: The name of the index
    :param doc_id: The document id (hash)
    :param fields: a {field: value} mapping of fields to update
    """
    # Mypy doesn't understand that body= has been deprecated already...
    es().update(index=index, id=doc_id, doc=fields)  # type: ignore


def _get_type_from_property(properties: dict) -> str:
    """
    Convert an elastic 'property' into an amcat4 field type
    """
    result = properties.get("meta", {}).get("amcat4_type")
    if result:
        return result
    return properties['type']


def get_fields(index: str) -> Mapping[str, dict]:
    """
    Get the field types in use in this index
    :param index:
    :return: a dict of fieldname: field objects {fieldname: {name, type, ...}]
    """
    r = es().indices.get_mapping(index=index)
    print(r[index]['mappings']['properties'])
    return {k: dict(name=k, type=_get_type_from_property(v))
            for k, v in r[index]['mappings']['properties'].items()}


def field_type(index: str, field_name: str) -> str:
    """
    Get the field type for the given field.
    :return: a type name ('text', 'date', ..)
    """
    # TODO: [WvA] cache this as it should be invariant
    return get_fields(index)[field_name]["type"]


def get_values(index: str, field: str) -> List[str]:
    """
    Get the values for a given field (e.g. to populate list of filter values on keyword field)
    :param index: The index
    :param field: The field name
    :return: A list of values
    """
    aggs = {"values": {"terms": {"field": field}}}
    r = es().search(index=index, size=0, aggs=aggs)
    return [x["key"] for x in r["aggregations"]["values"]["buckets"]]


def refresh(index: str):
    es().indices.refresh(index=index)


def index_exists(name: str) -> bool:
    """
    Check if an index with this name exists
    """
    return es().indices.exists(index=name)
