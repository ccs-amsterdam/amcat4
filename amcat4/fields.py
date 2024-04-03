"""
We have two types of fields:
- Elastic fields are the fields used under the hood by elastic. 
  (https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-types.html
  These are stored in the Mapping of an index
- Amcat fields (Field) are the fields are seen by the amcat user. They use a simplified type, and contain additional 
  information such as metareader access
  These are stored in the system index.

We need to make sure that:
- When a user sets a field, it needs to be changed in both types: the system index and the mapping
- If a field only exists in the elastic mapping, we need to add the default Field to the system index.
  This happens anytime get_fields is called, so that whenever a field is used it is guarenteed to be in the
  system index
"""

from hmac import new
import json
from tabnanny import check
from typing import Any, Iterator, Mapping, get_args, cast


from elasticsearch import NotFoundError
from httpx import get

# from amcat4.api.common import py2dict
from amcat4 import elastic
from amcat4.config import get_settings
from amcat4.elastic import es
from amcat4.models import FieldType, CreateField, ElasticType, Field, UpdateField, FieldMetareaderAccess


# given an elastic field type, Check if it is supported by AmCAT.
# this is not just the inverse of TYPEMAP_AMCAT_TO_ES because some AmCAT types map to multiple elastic
# types (e.g., tag and keyword, image_url and wildcard)
# (this is relevant if we are importing an index)
TYPEMAP_ES_TO_AMCAT: dict[ElasticType, FieldType] = {
    # TEXT fields
    "text": "text",
    "annotated_text": "text",
    "binary": "text",
    "match_only_text": "text",
    # DATE fields
    "date": "date",
    # BOOLEAN fields
    "boolean": "boolean",
    # KEYWORD fields
    "keyword": "keyword",
    "constant_keyword": "keyword",
    "wildcard": "keyword",
    # INTEGER fields
    "integer": "number",
    "byte": "number",
    "short": "number",
    "long": "number",
    "unsigned_long": "number",
    # NUMBER fields
    "float": "number",
    "half_float": "number",
    "double": "number",
    "scaled_float": "number",
    # OBJECT fields
    "object": "object",
    "flattened": "object",
    "nested": "object",
    # VECTOR fields (exclude sparse vectors)
    "dense_vector": "vector",
    # GEO fields
    "geo_point": "geo_point",
}

# maps amcat field types to elastic field types.
# The first elastic type in the array is the default.
TYPEMAP_AMCAT_TO_ES: dict[FieldType, list[ElasticType]] = {
    "text": ["text", "annotated_text", "binary", "match_only_text"],
    "date": ["date"],
    "boolean": ["boolean"],
    "keyword": ["keyword", "constant_keyword", "wildcard"],
    "number": ["double", "float", "half_float", "scaled_float"],
    "integer": ["long", "integer", "byte", "short", "unsigned_long"],
    "object": ["object", "flattened", "nested"],
    "vector": ["dense_vector"],
    "geo_point": ["geo_point"],
    "tag": ["keyword", "wildcard"],
    "image_url": ["wildcard", "keyword", "constant_keyword", "text"],
    "json": ["text"],
}


def get_default_metareader(type: FieldType):
    if type in ["boolean", "number", "date"]:
        return FieldMetareaderAccess(access="read")

    return FieldMetareaderAccess(access="none")


def get_default_field(type: FieldType):
    """
    Generate a field on the spot with default settings.
    Primary use case is importing existing indices with fields that are not registered in the system index.
    """
    elastic_type = TYPEMAP_AMCAT_TO_ES.get(type)
    if elastic_type is None:
        raise ValueError(
            f"The default elastic type mapping for field type {type} is not defined (if this happens, blame and inform Kasper)"
        )
    return Field(elastic_type=elastic_type[0], type=type, metareader=get_default_metareader(type))


def _standardize_createfields(fields: Mapping[str, FieldType | CreateField]) -> dict[str, CreateField]:
    sfields = {}
    for k, v in fields.items():
        if isinstance(v, str):
            assert v in get_args(ElasticType), f"Unknown elastic type {v}"
            sfields[k] = CreateField(type=cast(FieldType, v))
        else:
            sfields[k] = v
    return sfields


def check_forbidden_type(field: Field, type: FieldType):
    if field.identifier:
        for forbidden_type in ["tag", "vector"]:
            if type == forbidden_type:
                raise ValueError(f"Field {field} is an identifier field, which cannot be a {forbidden_type} field")


def coerce_type(value: Any, type: FieldType):
    """
    Coerces values into the respective type in elastic
    based on ES_MAPPINGS and elastic field types
    """
    if type in ["text", "tag", "image_url", "date"]:
        return str(value)
    if type in ["boolean"]:
        return bool(value)
    if type in ["number"]:
        return float(value)
    if type in ["integer"]:
        return int(value)

    if type == "json":
        if isinstance(value, str):
            return value
        return json.dumps(value)

    # TODO: check coercion / validation for object, vector and geo types
    if type in ["object"]:
        return value
    if type in ["vector"]:
        return value
    if type in ["geo_point"]:
        return value

    return value


def create_fields(index: str, fields: Mapping[str, FieldType | CreateField]):
    mapping: dict[str, Any] = {}
    current_fields = get_fields(index)

    sfields = _standardize_createfields(fields)

    for field, settings in sfields.items():
        if settings.elastic_type is not None:
            allowed_types = TYPEMAP_AMCAT_TO_ES.get(settings.type, [])
            if settings.elastic_type not in allowed_types:
                raise ValueError(
                    f"Field type {settings.type} does not support elastic type {settings.elastic_type}. "
                    f"Allowed types are: {allowed_types}"
                )
            elastic_type = settings.elastic_type
        else:
            elastic_type = get_default_field(settings.type).elastic_type

        current = current_fields.get(field)
        if current is not None:
            # fields can already exist. For example, a scraper might include the field types in every
            # upload request. If a field already exists, we'll ignore it, but we will throw an error
            # if static settings (elastic type, identifier) do not match.
            if current.elastic_type != elastic_type:
                raise ValueError(f"Field '{field}' already exists with elastic type '{current.elastic_type}'. ")
            if current.identifier != settings.identifier:
                raise ValueError(f"Field '{field}' already exists with identifier '{current.identifier}'. ")
            continue

        # if field does not exist, we add it to both the mapping and the system index
        mapping[field] = {"type": settings.type}
        if settings.type in ["date"]:
            mapping[field]["format"] = "strict_date_optional_time"

        current_fields[field] = Field(
            type=settings.type,
            elastic_type=elastic_type,
            identifier=settings.identifier,
            metareader=settings.metareader or get_default_metareader(settings.type),
            client_settings=settings.client_settings or {},
        )
        check_forbidden_type(current_fields[field], settings.type)

    if len(mapping) > 0:
        es().indices.put_mapping(index=index, properties=mapping)
        es().update(
            index=get_settings().system_index,
            id=index,
            doc=dict(fields=_fields_to_elastic(current_fields)),
        )


def _fields_to_elastic(fields: dict[str, Field]) -> list[dict]:
    # some additional validation
    return [{"field": field, "settings": settings.model_dump()} for field, settings in fields.items()]


def _fields_from_elastic(
    fields: list[dict],
) -> dict[str, Field]:
    return {fs["field"]: Field.model_validate(fs["settings"]) for fs in fields}


def update_fields(index: str, fields: dict[str, UpdateField]):
    """
    Set the fields settings for this index. Only updates fields that
    already exist. Only keys in UpdateField can be updated (not type or client_settings)
    """

    current_fields = get_fields(index)

    for field, new_settings in fields.items():
        current = current_fields.get(field)
        if current is None:
            raise ValueError(f"Field {field} does not exist")

        if new_settings.type is not None:
            check_forbidden_type(current, new_settings.type)

            valid_es_types = TYPEMAP_AMCAT_TO_ES.get(new_settings.type)
            if valid_es_types is None:
                raise ValueError(f"Invalid field type: {new_settings.type}")
            if current.elastic_type not in valid_es_types:
                raise ValueError(
                    f"Field {field} has the elastic type {current.elastic_type}. A {new_settings.type} field can only have the following elastic types: {valid_es_types}."
                )
            current_fields[field].type = new_settings.type

        if new_settings.metareader is not None:
            if current.type != "text" and new_settings.metareader.access == "snippet":
                raise ValueError(f"Field {field} is not of type text, cannot set metareader access to snippet")
            current_fields[field].metareader = new_settings.metareader

        if new_settings.client_settings is not None:
            current_fields[field].client_settings = new_settings.client_settings

    es().update(
        index=get_settings().system_index,
        id=index,
        doc=dict(fields=_fields_to_elastic(current_fields)),
    )


def _get_index_fields(index: str) -> Iterator[tuple[str, ElasticType]]:
    r = es().indices.get_mapping(index=index)

    if len(r[index]["mappings"]) > 0:
        for k, v in r[index]["mappings"]["properties"].items():
            yield k, v.get("type", "object")


def get_fields(index: str) -> dict[str, Field]:
    """
    Retrieve the fields settings for this index. Look for both the field settings in the system index,
    and the field mappings in the index itself. If a field is not defined in the system index, return the
    default settings for that field type and add it to the system index. This way, any elastic index can be imported
    """
    fields: dict[str, Field] = {}
    system_index = get_settings().system_index

    try:
        d = es().get(
            index=system_index,
            id=index,
            source_includes="fields",
        )
        system_index_fields = _fields_from_elastic(d["_source"].get("fields", {}))
    except NotFoundError:
        system_index_fields = {}

    update_system_index = False
    for field, elastic_type in _get_index_fields(index):
        type = TYPEMAP_ES_TO_AMCAT.get(elastic_type)

        if type is None:
            # skip over unsupported elastic fields.
            # (TODO: also return warning to client?)
            continue

        if field not in system_index_fields:
            update_system_index = True
            fields[field] = get_default_field(type)
        else:
            fields[field] = system_index_fields[field]

    if update_system_index:
        es().update(
            index=system_index,
            id=index,
            doc=dict(fields=_fields_to_elastic(fields)),
        )

    return fields


def create_or_verify_tag_field(index: str | list[str], field: str):
    """Create a special type of field that can be used to tag documents.
    Since adding/removing tags supports multiple indices, we first check whether the field name is valid for all indices"""
    indices = [index] if isinstance(index, str) else index
    add_to_indices = []
    for i in indices:
        current_fields = get_fields(i)
        if field in current_fields:
            if current_fields[field].type != "tag":
                raise ValueError(f"Field '{field}' already exists in index '{i}' and is not a tag field")

    else:
        add_to_indices.append(i)

    for i in add_to_indices:
        current_fields[field] = get_default_field("tag")
        es().indices.put_mapping(index=index, properties={field: {"type": "keyword"}})
        es().update(
            index=get_settings().system_index,
            id=i,
            doc=dict(fields=_fields_to_elastic(current_fields)),
        )


def field_values(index: str, field: str, size: int) -> list[str]:
    """
    Get the values for a given field (e.g. to populate list of filter values on keyword field)
    Results are sorted descending by document frequency
    see: https://www.elastic.co/guide/en/elasticsearch/reference/7.4/search-aggregations-bucket-terms-aggregation.html
         #search-aggregations-bucket-terms-aggregation-order

    :param index: The index
    :param field: The field name
    :return: A list of values
    """
    aggs = {"unique_values": {"terms": {"field": field, "size": size}}}
    r = es().search(index=index, size=0, aggs=aggs)
    return [x["key"] for x in r["aggregations"]["unique_values"]["buckets"]]


def field_stats(index: str, field: str) -> list[str]:
    """
    :param index: The index
    :param field: The field name
    :return: A list of values
    """
    aggs = {"facets": {"stats": {"field": field}}}
    r = es().search(index=index, size=0, aggs=aggs)
    return r["aggregations"]["facets"]


def update_by_query(index: str | list[str], script: str, query: dict, params: dict | None = None):
    script_dict = dict(source=script, lang="painless", params=params or {})
    es().update_by_query(index=index, script=script_dict, **query)
