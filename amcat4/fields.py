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

import datetime
import json
from typing import Any, Iterable, Iterator, Mapping, cast, get_args

from elasticsearch import NotFoundError

# from amcat4.api.common import py2dict
from amcat4.config import get_settings
from amcat4.elastic import es
from amcat4.models import ElasticType, Field, FieldMetareaderAccess, FieldType, PartialField

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
    "image": ["wildcard", "keyword", "constant_keyword", "text"],
    "video": ["wildcard", "keyword", "constant_keyword", "text"],
    "audio": ["wildcard", "keyword", "constant_keyword", "text"],
    "url": ["wildcard", "keyword", "constant_keyword", "text"],
    "json": ["text"],
}


def coerce_type(value: Any, type: FieldType):
    """
    Coerces values into the respective type in elastic
    based on ES_MAPPINGS and elastic field types
    """
    if type == "date" and isinstance(value, datetime.date):
        return value.isoformat()
    if type == "tag" and isinstance(value, Iterable) and not isinstance(value, str):
        return [str(val) for val in value]
    if type in ["text", "tag", "image", "video", "audio", "date"]:
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


def _check_type_compatibility(new_field: PartialField, existing_field: Field | None):
    """Check whether new_field is compatible with existing_field, raise ValueError otherwise"""
    # If there is no existing field, or if the new field doesn't specify a type, no need to check compatibility
    if existing_field is None:
        return
    if new_field.elastic_type is None and new_field.type is None:
        return
    # If elastic type is given, it needs to be identical to the existing type
    if new_field.elastic_type != existing_field.elastic_type:
        raise ValueError("Cannot change the elastic type of existing fields")
    # If elastic type is not given, the given amcat type needs to be compatible with the existing elastic type
    if new_field.elastic_type is None:
        assert new_field.type is not None
        compatible_fields = TYPEMAP_AMCAT_TO_ES[new_field.type]
        if existing_field.elastic_type not in compatible_fields:
            raise ValueError(
                f"Field type {new_field.type} is not compatible with existing elastic type"
                f" (compatible fields: {compatible_fields})"
            )


def _get_elastic_mapping(field: PartialField):
    result = {"type": field.elastic_type}
    if field.type in ["date"]:
        result["format"] = "strict_date_optional_time"
    return result


def _set_new_field_defaults(field: PartialField) -> Field:
    """Populate field with default values where needed"""
    if field.elastic_type is None:
        assert field.type is not None
        field.elastic_type = TYPEMAP_AMCAT_TO_ES[field.type][0]
    if field.type is None:
        field.type = TYPEMAP_ES_TO_AMCAT[field.elastic_type]
    if field.metareader is None:
        field.metareader = FieldMetareaderAccess(access="none" if field.type in ["text"] else "read")
    if field.identifier is None:
        field.identifier = False
    return Field.model_validate(field, from_attributes=True)


def _update_field(new: PartialField, existing: Field) -> Field:
    """Update existing field with all not-None fields in source, returning an updated field"""
    source_fields = {k: v for (k, v) in new.model_dump().items() if v is not None}
    return Field.model_validate(existing.model_dump() | source_fields)


def set_fields(index: str, fields: Mapping[str, PartialField]):
    """Create or update the definition of fields in this index

    This will create any field in fields that does not exist in the index, and update existing fields.
    As fields in Elastic are quite rigid, a number of conditions need to be met:

    - Elastic type and (AmCAT) field type need to be compatible
    - Cannot change the elastic type of existing fields
    - Cannot change identifiers if index already has data

    Args:
        index (str): Name of the index
        fields (Mapping[str, Field]): A mapping of field name to Field definition

    Raises:
        ValueError: If any of the conditions above are not met
    """
    existing_fields = get_fields(index)
    updated_fields = {name: field.model_copy() for (name, field) in existing_fields.items()}
    new_elastic_fields_mapping: dict[str, Any] = {}
    amcat_field_updates: dict[str, Any] = {}
    identifiers_have_changed = False

    for name, field in fields.items():
        existing = existing_fields.get(name)
        _check_type_compatibility(field, existing)
        if field.identifier != (existing.identifier if existing else False):
            identifiers_have_changed = True
        if existing:
            updated_fields[name] = _update_field(field, existing)
        else:
            updated_fields[name] = _set_new_field_defaults(field)
            new_elastic_fields_mapping[name] = _get_elastic_mapping(field)

    if identifiers_have_changed:
        # new identifiers are only allowed if the index is a new index (i.e. no documents)
        if es().count(index=index)["count"] > 0:
            raise ValueError("Cannot add identifiers to a non-empty index")

    if len(new_elastic_fields_mapping) > 0:
        es().indices.put_mapping(index=index, properties=new_elastic_fields_mapping)

    if updated_fields != existing_fields:
        es().update(
            index=get_settings().system_index,
            id=index,
            doc=dict(fields=_fields_to_elastic(updated_fields)),
        )


def _fields_to_elastic(fields: dict[str, Field]) -> list[dict]:
    # some additional validation
    return [{"field": field, "settings": settings.model_dump()} for field, settings in fields.items()]


def _fields_from_elastic(fields: list[dict]) -> dict[str, Field]:
    try:
        return {f["field"]: Field.model_validate(f["settings"]) for f in fields}
    except ValueError as e:
        # Note - recasting ValueError as it confuses fastapi into thinking it's an input problem
        raise Exception(e)


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
    d = es().get(
        index=get_settings().system_index,
        id=index,
        source_includes="fields",
    )
    system_index_fields = _fields_from_elastic(d["_source"].get("fields", []))
    for field, elastic_type in _get_index_fields(index):
        type = TYPEMAP_ES_TO_AMCAT.get(elastic_type)

        if type is None:
            # skip over unsupported elastic fields.
            # (TODO: also return warning to client?)
            continue

        if field not in system_index_fields:
            fields[field] = _set_new_field_defaults(PartialField(type=type))
        else:
            fields[field] = system_index_fields[field]

    return fields


def create_or_verify_tag_field(index: str | list[str], field: str):
    """Create a special type of field that can be used to tag documents.
    Since adding/removing tags supports multiple indices, we first check whether the field name is valid for all indices"""
    indices = [index] if isinstance(index, str) else index
    add_to_indices = []
    for ix in indices:
        current_fields = get_fields(ix)
        if field in current_fields:
            if current_fields[field].type != "tag":
                raise ValueError(f"Field '{field}' already exists in index '{ix}' and is not a tag field")

    else:
        add_to_indices.append(ix)

    for ix in add_to_indices:
        set_fields(index=ix, fields={field: PartialField(type="tag")})


def field_values(index: str, field: str, size: int = 2000) -> list[str]:
    """
    Get the values for a given field (e.g. to populate list of filter values on keyword field)
    This combines the values from the metadata (value + name + description) and from elastic (value + n)
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
