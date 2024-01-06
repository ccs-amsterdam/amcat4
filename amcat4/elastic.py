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
import re
from typing import Mapping, List, Iterable, Optional, Tuple, Union, Sequence, Literal

from elasticsearch import Elasticsearch, NotFoundError
from elasticsearch.helpers import bulk

from amcat4.config import get_settings
from amcat4.util import parse_snippet

SYSTEM_INDEX_VERSION = 1

ES_MAPPINGS = {
    "long": {"type": "long", "meta": {"metareader_access": "read"}},
    "date": {
        "type": "date",
        "format": "strict_date_optional_time",
        "meta": {"metareader_access": "read"},
    },
    "double": {"type": "double", "meta": {"metareader_access": "read"}},
    "keyword": {"type": "keyword", "meta": {"metareader_access": "read"}},
    "url": {
        "type": "keyword",
        "meta": {"amcat4_type": "url", "metareader_access": "read"},
    },
    "tag": {
        "type": "keyword",
        "meta": {"amcat4_type": "tag", "metareader_access": "read"},
    },
    "id": {
        "type": "keyword",
        "meta": {"amcat4_type": "id", "metareader_access": "read"},
    },
    "text": {"type": "text", "meta": {"metareader_access": "none"}},
    "object": {"type": "object", "meta": {"metareader_access": "none"}},
    "geo_point": {"type": "geo_point", "metareader_access": "read"},
    "dense_vector": {"type": "dense_vector", "metareader_access": "none"},
}

DEFAULT_MAPPING = {
    "text": ES_MAPPINGS["text"],
    "title": ES_MAPPINGS["text"],
    "date": ES_MAPPINGS["date"],
    "url": ES_MAPPINGS["url"],
}


SYSTEM_MAPPING = {
    "name": {"type": "text"},
    "description": {"type": "text"},
    "roles": {"type": "nested"},
    "summary_field": {"type": "keyword"},
    "guest_role": {"type": "keyword"},
}


class CannotConnectElastic(Exception):
    pass


@functools.lru_cache()
def es() -> Elasticsearch:
    try:
        return _setup_elastic()
    except ValueError as e:
        raise ValueError(
            f"Cannot connect to elastic {get_settings().elastic_host!r}: {e}"
        )


def connect_elastic() -> Elasticsearch:
    """
    Connect to the elastic server using the system settings
    """
    settings = get_settings()
    if settings.elastic_password:
        return Elasticsearch(
            settings.elastic_host or None,
            basic_auth=("elastic", settings.elastic_password),
            verify_certs=settings.elastic_verify_ssl,
        )
    else:
        return Elasticsearch(settings.elastic_host or None)


def get_system_version(elastic=None) -> Optional[int]:
    """
    Get the elastic system index version
    """
    # WvA: I don't like this 'circular' import. Should probably reorganize the elastic and index modules
    from amcat4.index import GLOBAL_ROLES

    settings = get_settings()
    if elastic is None:
        elastic = es()
    try:
        r = elastic.get(
            index=settings.system_index, id=GLOBAL_ROLES, source_includes="version"
        )
    except NotFoundError:
        return None
    return r["_source"]["version"]


def _setup_elastic():
    """
    Check whether we can connect with elastic
    """
    # WvA: I don't like this 'circular' import. Should probably reorganize the elastic and index modules
    from amcat4.index import GLOBAL_ROLES

    settings = get_settings()
    logging.debug(
        f"Connecting with elasticsearch at {settings.elastic_host}, "
        f"password? {'yes' if settings.elastic_password else 'no'} "
    )
    elastic = connect_elastic()
    if not elastic.ping():
        raise CannotConnectElastic(
            f"Cannot connect to elasticsearch server {settings.elastic_host}"
        )
    if elastic.indices.exists(index=settings.system_index):
        # Check index format version
        if get_system_version(elastic) is None:
            raise CannotConnectElastic(
                f"System index {settings.elastic_host}::{settings.system_index} is corrupted or uses an "
                f"old format. Please repair or migrate before continuing"
            )

    else:
        logging.info(f"Creating amcat4 system index: {settings.system_index}")
        elastic.indices.create(
            index=settings.system_index, mappings={"properties": SYSTEM_MAPPING}
        )
        elastic.index(
            index=settings.system_index,
            id=GLOBAL_ROLES,
            document=dict(version=SYSTEM_INDEX_VERSION, roles=[]),
        )
    return elastic


def coerce_type_to_elastic(value, ftype):
    """
    Coerces values into the respective type in elastic
    based on ES_MAPPINGS and elastic field types
    """
    if ftype in ["keyword", "constant_keyword", "wildcard", "url", "tag", "text"]:
        value = str(value)
    elif ftype in [
        "long",
        "short",
        "byte",
        "double",
        "float",
        "half_float",
        "half_float",
        "unsigned_long",
    ]:
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
    hash_str = json.dumps(
        document, sort_keys=True, ensure_ascii=True, default=str
    ).encode("ascii")
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
                    document[key] = coerce_type_to_elastic(
                        document[key], field_types[key].get("type")
                    )
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
        mapping = ES_MAPPINGS[type_["type"]]
        meta = mapping.get("meta", {})
        if m := type_.get("meta"):
            meta.update(m)
        mapping["meta"] = validate_field_meta(meta)
        return mapping


def validate_field_meta(meta: dict):
    """
    Elastic has limited available field meta. Here we validate the allowed keys (and values)
    """
    valid_fields = ["amcat4_type", "metareader_access", "client_display"]

    for meta_field in meta.keys():
        # Validate keys
        if meta_field not in valid_fields:
            raise ValueError(f"Invalid meta field: {meta_field}")

        # Validate values
        if not isinstance(meta[meta_field], str):
            raise ValueError("Meta field value has to be a string")

        if meta_field == "amcat4_type":
            if meta[meta_field] not in ES_MAPPINGS.keys():
                raise ValueError(f"Invalid amcat4_type value: {meta[meta_field]}")

        if meta_field == "client_display":
            # client_display only concerns the client
            continue

        if meta_field == "metareader_access":
            # metareader_access can be "none", "read", or "snippet"
            # if snippet, can also include the maximum snippet parameters (nomatch_chars, max_matches, match_chars)
            # in the format: snippet[nomatch_chars;max_matches;match_chars]
            reg = r"^(read|none|snippet(\[\d+;\d+;\d+\])?)$"
            if not re.match(reg, meta[meta_field]):
                raise ValueError(f"Invalid metareader_access value: {meta[meta_field]}")

    return meta


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
    return es().get(index=index, id=doc_id, **kargs)["_source"]


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
    properties["type"] = properties.get("type", "object")
    if result:
        return result
    return properties["type"]


def _get_fields(index: str) -> Iterable[Tuple[str, dict]]:
    r = es().indices.get_mapping(index=index)
    for k, v in r[index]["mappings"]["properties"].items():
        t = dict(name=k, type=_get_type_from_property(v))
        if meta := v.get("meta"):
            t["meta"] = meta
        yield k, t


def get_index_fields(index: str) -> Mapping[str, dict]:
    """
    Get the field types in use in this index
    :param index:
    :return: a dict of fieldname: field objects {fieldname: {name, type, meta, ...}]
    """
    return dict(_get_fields(index))


def get_fields(index: Union[str, Sequence[str]]) -> Mapping[str, dict]:
    """
    Get the field types in use in this index or indices
    :param index: name(s) of index(es) to query
    :return: a dict of fieldname: field objects {fieldname: {name, type, ...}]
    """
    if isinstance(index, str):
        return get_index_fields(index)

    # def get_meta_value(field, meta_key, default):
    #     return field.get("meta", {}).get(meta_key) or default

    # def get_least_metareader_access(access1, access2):
    #     if (access1 == None) or (access2 == None):
    #         return None

    #     if "snippet" in access1 and access2 == "read":
    #         return access1

    #     if "snippet" in access2 and access1 == "read":
    #         return access2

    #     if "snippet" in access1 and "snippet" in access2:
    #         _, nomatch_chars1, max_matches1, match_chars1 = parse_snippet(access1)
    #         _, nomatch_chars2, max_matches2, match_chars2 = parse_snippet(access2)
    #         nomatch_chars = min(nomatch_chars1, nomatch_chars2)
    #         max_matches = min(max_matches1, max_matches2)
    #         match_chars = match_chars1 + match_chars2
    #         return f"snippet[{nomatch_chars},{max_matches},{match_chars}]"

    #     if access1 == "read" and access2 == "read":
    #         return "read"

    result = {}
    for ix in index:
        for f, ftype in get_index_fields(ix).items():
            if f in result:
                if result[f] != ftype:
                    # note that for merged fields metareader access is always None
                    # metareader_access_1: bool = get_meta_value(
                    #     result[f], "metareader_visible", None
                    # )
                    # metareader_access_2: bool = get_meta_value(
                    #     ftype, "metareader_visible", None
                    # )
                    # metareader_access = get_least_metareader_access(
                    #     metareader_access_1, metareader_access_2
                    # )

                    result[f] = {
                        "name": f,
                        "type": "keyword",
                        "meta": {
                            "merged": True,
                        },
                    }
            else:
                result[f] = ftype
    return result


def get_field_values(index: str, field: str, size: int) -> List[str]:
    """
    Get the values for a given field (e.g. to populate list of filter values on keyword field)
    Results are sorted descending by document frequency
    see: https://www.elastic.co/guide/en/elasticsearch/reference/7.4/search-aggregations-bucket-terms-aggregation.html#search-aggregations-bucket-terms-aggregation-order

    :param index: The index
    :param field: The field name
    :return: A list of values
    """
    aggs = {"unique_values": {"terms": {"field": field, "size": size}}}
    r = es().search(index=index, size=0, aggs=aggs)
    return [x["key"] for x in r["aggregations"]["unique_values"]["buckets"]]


def get_field_stats(index: str, field: str) -> List[str]:
    """
    Get field statistics, such as min, max, avg, etc.
    :param index: The index
    :param field: The field name
    :return: A list of values
    """
    aggs = {"facets": {"stats": {"field": field}}}
    r = es().search(index=index, size=0, aggs=aggs)
    return r["aggregations"]["facets"]


def update_by_query(index: str, script: str, query: dict, params: dict = None):
    script = dict(source=script, lang="painless", params=params or {})
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
    }""",
)


def update_tag_by_query(
    index: str, action: Literal["add", "remove"], query: dict, field: str, tag: str
):
    script = TAG_SCRIPTS[action]
    params = dict(field=field, tag=tag)
    update_by_query(index, script, query, params)


def ping():
    """
    Can we reach this elasticsearch server
    """
    try:
        return es().ping()
    except CannotConnectElastic as e:
        logging.error(e)
        return False
