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
from typing import Any, Iterator, Mapping, get_args, cast


from elasticsearch import NotFoundError

# from amcat4.api.common import py2dict
from amcat4.config import get_settings
from amcat4.elastic import es
from amcat4.models import TypeGroup, CreateField, ElasticType, Field, UpdateField, FieldMetareaderAccess


# given an elastic field type, infer
# (this is relevant if we are importing an index that does not yet have )
TYPEMAP_ES_TO_AMCAT: dict[ElasticType, TypeGroup] = {
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
    # NUMBER fields
    # - integer
    "integer": "number",
    "byte": "number",
    "short": "number",
    "long": "number",
    "unsigned_long": "number",
    # - float
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
    "geo_point": "geo",
}


def get_default_metareader(type_group: TypeGroup):
    if type_group in ["boolean", "number", "date"]:
        return FieldMetareaderAccess(access="read")

    return FieldMetareaderAccess(access="none")


def get_default_field(elastic_type: ElasticType):
    type_group = TYPEMAP_ES_TO_AMCAT.get(elastic_type)
    if type_group is None:
        raise ValueError(f"Invalid elastic type: {elastic_type}")

    return Field(type_group=type_group, type=elastic_type, metareader=get_default_metareader(type_group))


def _standardize_createfields(fields: Mapping[str, ElasticType | CreateField]) -> dict[str, CreateField]:
    sfields = {}
    for k, v in fields.items():
        if isinstance(v, str):
            assert v in get_args(ElasticType), f"Unknown elastic type {v}"
            sfields[k] = CreateField(type=cast(ElasticType, v))
        else:
            sfields[k] = v
    return sfields


def coerce_type(value: Any, elastic_type: ElasticType):
    """
    Coerces values into the respective type in elastic
    based on ES_MAPPINGS and elastic field types
    """
    if elastic_type in ["text", "annotated_text", "binary", "match_only_text", "keyword", "constant_keyword", "wildcard"]:
        return str(value)
    if elastic_type in ["boolean"]:
        return bool(value)
    if elastic_type in ["long", "integer", "short", "byte", "unsigned_long"]:
        return int(value)
    if elastic_type in ["float", "half_float", "double", "scaled_float"]:
        return float(value)

    # TODO: check coercion / validation for object, vector and geo types
    if elastic_type in ["object", "flattened", "nested"]:
        return value
    if elastic_type in ["dense_vector"]:
        return value
    if elastic_type in ["geo_point"]:
        return value

    return value


def create_fields(index: str, fields: Mapping[str, ElasticType | CreateField]):
    mapping: dict[str, Any] = {}
    current_fields = get_fields(index)

    new_fields: dict[str, Field] = {}

    sfields = _standardize_createfields(fields)

    for field, settings in sfields.items():
        if TYPEMAP_ES_TO_AMCAT.get(settings.type) is None:
            raise ValueError(f"Field type {settings.type} not supported by AmCAT")

        current = current_fields.get(field)
        if current is not None:
            # fields can already exist. For example, a scraper might include the field types in every
            # upload request. If a field already exists, we'll ignore it, but we will throw an error
            # if static settings (field type, identifier) do not match
            if current.type != settings.type:
                raise ValueError(
                    f"Field '{field}' already exists with type '{current.type}'. " f"Cannot change type to '{settings.type}'"
                )
            if current.identifier and not settings.identifier:
                raise ValueError(f"Field '{field}' is an identifier, cannot change to non-identifier")
            if not current.identifier and settings.identifier:
                raise ValueError(f"Field '{field}' is not an identifier, cannot change to identifier")
            new_fields[field] = current
        else:
            # if field does not exist, we add it to both the mapping and the system index
            mapping[field] = {"type": settings.type}
            if settings.type in ["date"]:
                mapping[field]["format"] = "strict_date_optional_time"

            new_fields[field] = Field(
                type=settings.type,
                type_group=TYPEMAP_ES_TO_AMCAT[settings.type],
                identifier=settings.identifier,
                metareader=settings.metareader or get_default_metareader(TYPEMAP_ES_TO_AMCAT[settings.type]),
                client_settings=settings.client_settings or {},
            )
    print(mapping)
    if len(mapping) > 0:
        es().indices.put_mapping(index=index, properties=mapping)
        es().update(
            index=get_settings().system_index,
            id=index,
            doc=dict(fields=_fields_to_elastic(new_fields)),
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
        type_group = TYPEMAP_ES_TO_AMCAT.get(elastic_type)

        if type_group is None:
            # skip over unsupported elastic fields.
            # (TODO: also return warning to client?)
            continue

        if field not in system_index_fields:
            update_system_index = True
            fields[field] = get_default_field(elastic_type)
        else:
            fields[field] = system_index_fields[field]

    if update_system_index:
        es().update(
            index=system_index,
            id=index,
            doc=dict(fields=_fields_to_elastic(fields)),
        )

    return fields


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
