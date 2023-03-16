"""
Connection between AmCAT4 and the elasticsearch backend

Some things to note:
- See config.py for global settings, including elastic host and system index name
- The elasticsearch backend should contain a system index, which will be created if needed
- The system index contains a 'document' for each used index containing:
  {auth: [{email: role}], guest_role: role}
- We define the mappings (field types) based on existing elasticsearch mappings,
  but use field metadata to define specific fields, see ES_MAPPINGS below.
"""
import functools
import hashlib
import json
import logging
from typing import Mapping, List, Iterable, Tuple, Union, Sequence, Literal

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from amcat4.config import get_settings

ES_MAPPINGS = {
   'long': {"type": "long"},
   'date': {"type": "date", "format": "strict_date_optional_time"},
   'double': {"type": "double"},
   'keyword': {"type": "keyword"},
   'url': {"type": "keyword", "meta": {"amcat4_type": "url"}},
   'tag': {"type": "keyword", "meta": {"amcat4_type": "tag"}},
   'id': {"type": "keyword", "meta": {"amcat4_type": "id"}},
   'text': {"type": "text"},
   'object': {"type": "object"},
   'geo_point': {"type": "geo_point"}
   }

DEFAULT_MAPPING = {
    'text': ES_MAPPINGS['text'],
    'title': ES_MAPPINGS['text'],
    'date': ES_MAPPINGS['date'],
    'url': ES_MAPPINGS['url'],
}

SYSTEM_MAPPING = {
    'index': {"type": "keyword"},
    'email': {"type": "keyword"},
    'role': {"type": "keyword"},
}


@functools.lru_cache()
def es() -> Elasticsearch:
    try:
        return _setup_elastic()
    except ValueError as e:
        raise ValueError(f"Cannot connect to elastic {get_settings().elastic_host!r}: {e}")


def _setup_elastic():
    """
    Check whether we can connect with elastic
    """
    settings = get_settings()
    logging.debug(f"Connecting with elasticsearch at {settings.elastic_host}, "
                  "password? {'yes' if settings.elastic_password else 'no'} ")
    if settings.elastic_password:
        elastic = Elasticsearch(settings.elastic_host or None,
                                basic_auth=("elastic", settings.elastic_password),
                                verify_certs=settings.elastic_verify_ssl)
    else:
        elastic = Elasticsearch(settings.elastic_host or None)
    if not elastic.ping():
        raise Exception(f"Cannot connect to elasticsearch server {settings.elastic_host}")
    if not elastic.indices.exists(index=settings.system_index):
        logging.info(f"Creating amcat4 system index: {settings.system_index}")
        elastic.indices.create(index=settings.system_index, mappings={'properties': SYSTEM_MAPPING})
    return elastic


def coerce_type_to_elastic(value, ftype):
    """
    Coerces values into the respective type in elastic
    based on ES_MAPPINGS and elastic field types
    """
    if ftype in ["keyword",
                 "constant_keyword",
                 "wildcard",
                 "url",
                 "tag",
                 "text"]:
        value = str(value)
    elif ftype in ["long",
                   "short",
                   "byte",
                   "double",
                   "float",
                   "half_float",
                   "half_float",
                   "unsigned_long"]:
        value = float(value)
    elif ftype in ["integer"]:
        value = int(value)
    elif ftype == "boolean":
        value = bool(value)
    return value


def _get_hash(document: dict) -> bytes:
    """
    Get the hash for a document
    """
    hash_str = json.dumps(document, sort_keys=True, ensure_ascii=True, default=str).encode('ascii')
    m = hashlib.sha224()
    m.update(hash_str)
    return m.hexdigest()


def upload_documents(index: str, documents, fields: Mapping[str, str] = None) -> None:
    """
    Upload documents to this index

    :param index: The name of the index (without prefix)
    :param documents: A sequence of article dictionaries
    :param fields: A mapping of field:type for field types
    """
    def es_actions(index, documents):
        field_types = get_index_fields(index)
        for document in documents:
            for key in document.keys():
                if key in field_types:
                    document[key] = coerce_type_to_elastic(document[key], field_types[key].get("type"))
            if "_id" not in document:
                document["_id"] = _get_hash(document)
            yield {"_index": index, **document}

    if fields:
        set_fields(index, fields)

    actions = list(es_actions(index, documents))
    bulk(es(), actions)


def get_field_mapping(type_: Union[str, dict]):
    if isinstance(type_, str):
        return ES_MAPPINGS[type_]
    else:
        mapping = ES_MAPPINGS[type_['type']]
        meta = mapping.get('meta', {})
        if m := type_.get('meta'):
            meta.update(m)
        mapping['meta'] = meta
        return mapping


def set_fields(index: str, fields: Mapping[str, str]):
    """
    Update the column types for this index

    :param index: The name of the index (without prefix)
    :param fields: A mapping of field:type for column types
    """
    properties = {field: get_field_mapping(type_) for (field, type_) in fields.items()}
    es().indices.put_mapping(index=index, properties=properties)


def get_document(index: str, doc_id: str, **kargs) -> dict:
    """
    Get a single document from this index.

    :param index: The name of the index
    :param doc_id: The document id (hash)
    :return: the source dict of the document
    """
    return es().get(index=index, id=doc_id, **kargs)['_source']


def update_document(index: str, doc_id: str, fields: dict):
    """
    Update a single document.

    :param index: The name of the index
    :param doc_id: The document id (hash)
    :param fields: a {field: value} mapping of fields to update
    """
    # Mypy doesn't understand that body= has been deprecated already...
    es().update(index=index, id=doc_id, doc=fields)  # type: ignore


def delete_document(index: str, doc_id: str):
    """
    Delete a single document

    :param index: The name of the index
    :param doc_id: The document id (hash)
    """
    es().delete(index=index, id=doc_id)


def _get_type_from_property(properties: dict) -> str:
    """
    Convert an elastic 'property' into an amcat4 field type
    """
    result = properties.get("meta", {}).get("amcat4_type")
    if result:
        return result
    return properties['type']


def _get_fields(index: str) -> Iterable[Tuple[str, dict]]:
    r = es().indices.get_mapping(index=index)
    for k, v in r[index]['mappings']['properties'].items():
        t = dict(name=k, type=_get_type_from_property(v))
        if meta := v.get('meta'):
            t['meta'] = meta
        yield k, t


def get_index_fields(index: str) -> Mapping[str, dict]:
    """
    Get the field types in use in this index
    :param index:
    :return: a dict of fieldname: field objects {fieldname: {name, type, meta, ...}]
    """
    return dict(_get_fields(index))


def get_fields(index: Union[str, Sequence[str]]):
    """
    Get the field types in use in this index or indices
    :param index: name(s) of index(es) to query
    :return: a dict of fieldname: field objects {fieldname: {name, type, ...}]
    """
    if isinstance(index, str):
        return get_index_fields(index)
    result = {}
    for ix in index:
        for f, ftype in get_index_fields(ix).items():
            if f in result:
                if result[f] != ftype:
                    result[f] = {"name": f, "type": "keyword", "meta": {"merged": True}}
            else:
                result[f] = ftype
    return result


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


def update_by_query(index: str, script: str, query: dict, params: dict = None):
    script = dict(
        source=script,
        lang="painless",
        params=params or {}
    )
    es().update_by_query(index=index, script=script, **query)


TAG_SCRIPTS = dict(
    add="""
    if (ctx._source[params.field] == null) {
      ctx._source[params.field] = [params.tag]
    } else if (!ctx._source[params.field].contains(params.tag)) {
      ctx._source[params.field].add(params.tag)
    }
    """,
    remove="""
    if (ctx._source[params.field] != null && ctx._source[params.field].contains(params.tag)) {
      ctx._source[params.field].removeAll([params.tag]);
      if (ctx._source[params.field].size() == 0) {
        ctx._source.remove(params.field);
      }
    }""")


def update_tag_by_query(index: str, action: Literal["add", "remove"], query: dict, field: str, tag: str):
    script = TAG_SCRIPTS[action]
    params = dict(field=field, tag=tag)
    update_by_query(index, script, query, params)


def ping():
    """
    Can we reach this elasticsearch server
    """
    return es().ping()
