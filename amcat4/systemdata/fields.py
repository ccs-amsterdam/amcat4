"""
We have two types of fields:
- Elastic fields are the fields used under the hood by elastic.
  (https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-types.html
  These are stored in the Mapping of an index
- Amcat fields (Field) are the fields are seen by the amcat user. They use a simplified type, and contain additional
  information such as metareader access
  These are stored in the "fields" system index

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
from fastapi import HTTPException

from amcat4.elastic import es
from amcat4.models import CreateField, ElasticType, Field, FieldMetareaderAccess, FieldSpec, FieldType, Role, UpdateField, User
from amcat4.systemdata.roles import get_project_role, role_is_at_least
from amcat4.systemdata.versions.v2 import FIELDS_INDEX, fields_index_id
from amcat4.systemdata.util import BulkInsertAction, es_bulk_upsert, index_scan


def elastic_update_fields(index: str, fields: dict[str, Field]):
    def insert_fields():
        for field, settings in fields.items():
            id = fields_index_id(index, field)
            field_doc = {"field": field, "settings": settings.model_dump()}
            yield BulkInsertAction(index=FIELDS_INDEX, id=id, doc=field_doc)

    es_bulk_upsert(insert_fields())


def elastic_list_fields(index: str) -> dict[str, Field]:
    docs = index_scan(FIELDS_INDEX, query={"term": {"index": index}})
    return {doc["field"]: Field.model_validate(doc["settings"]) for id, doc in docs}


# TODO: there is now a lot of complexity because we allow querying multiple indices at once.
# I think we should instead:
# - Create a 'discovery' endpoint that given a query returns all public indices that match the query,
#   with field access information (and possibly document counts).
#   (This can then even be used to discover indices across servers!!)
# - If users want data from multiple indices, they then just need to make multiple requests, one per index.
#   With the discovery endpoint, we can provide UI / helper functions for this.
#
#

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
            assert v in get_args(FieldType), f"Unknown amcat type {v}"
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


def create_fields(index: str, fields: Mapping[str, FieldType | CreateField]):
    mapping: dict[str, Any] = {}
    current_fields = get_fields(index)

    sfields = _standardize_createfields(fields)
    old_identifiers = any(f.identifier for f in current_fields.values())
    new_identifiers = False

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
        if settings.identifier:
            new_identifiers = True
        mapping[field] = {"type": elastic_type}
        if settings.type in ["date"]:
            mapping[field]["format"] = "strict_date_optional_time"

        current_fields[field] = Field(
            type=settings.type,
            elastic_type=elastic_type,
            identifier=settings.identifier,
            metareader=settings.metareader or get_default_metareader(settings.type),
        )
        check_forbidden_type(current_fields[field], settings.type)

    if new_identifiers:
        # new identifiers are only allowed if the index had identifiers, or if it is a new index (i.e. no documents)
        has_docs = es().count(index=index)["count"] > 0
        if has_docs and not old_identifiers:
            raise ValueError("Cannot add identifiers. Index already has documents with no identifiers.")

    if len(mapping) > 0:
        es().indices.put_mapping(index=index, properties=mapping)
        elastic_update_fields(index, current_fields)


def update_fields(index: str, fields: dict[str, UpdateField]):
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
                    f"Field {field} has the elastic type {current.elastic_type}. A {new_settings.type} "
                    "field can only have the following elastic types: {valid_es_types}."
                )
            current_fields[field].type = new_settings.type

        if new_settings.metareader is not None:
            if current.type != "text" and new_settings.metareader.access == "snippet":
                raise ValueError(f"Field {field} is not of type text, cannot set metareader access to snippet")
            current_fields[field].metareader = new_settings.metareader

        if new_settings.client_settings is not None:
            current_fields[field].client_settings = new_settings.client_settings

    elastic_update_fields(index, current_fields)


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

    try:
        system_index_fields = elastic_list_fields(index)
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
        elastic_update_fields(index, fields)

    return fields


def create_or_verify_tag_field(index: str | list[str], field: str):
    """
    Create a special type of field that can be used to tag documents.
    Since adding/removing tags supports multiple indices, we first check whether the field name is valid for all indices
    TODO: double check, because this function looks weird
    """
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
        current_fields = get_fields(i)
        current_fields[field] = get_default_field("tag")
        es().indices.put_mapping(index=index, properties={field: {"type": "keyword"}})
        elastic_update_fields(i, current_fields)


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


def raise_if_field_not_allowed(index: str, user: User, fields: list[FieldSpec]) -> None:
    """
    If the current user is a metareader (!!needs to be confirmed by caller),
    check if they are allowed to query the given fields and snippets on the given index.

    :param index: The index to check the role on
    :param user: The email address of the authenticated user
    :param fields: The fields to check
    :param snippets: The snippets to check
    :return: Nothing. Throws HTTPException if the user is not allowed to query the given fields and snippets.
    """
    role = get_project_role(user.email, index)
    if not role_is_at_least(role, Role.METAREADER):
        raise HTTPException(
            status_code=403,
            detail=f"User {user.email} does not have permission to access index {index}",
        )
    if role_is_at_least(role, Role.READER):
        return

    if fields is None or len(fields) == 0:
        return None

    index_fields = get_fields(index)
    for field in fields:
        if field.name not in index_fields:
            # Should we raise an error here? If we want to support querying multiple
            # indices at once, not throwing an error allows the user to query fields
            # that do not exist on all indices
            continue
        metareader = index_fields[field.name].metareader

        if metareader.access == "read":
            continue
        elif metareader.access == "snippet" and metareader.max_snippet is not None:
            if metareader.max_snippet is None:
                max_params_msg = ""
            else:
                max_params_msg = (
                    "Can only read snippet with max parameters:"
                    f" nomatch_chars={metareader.max_snippet.nomatch_chars}"
                    f", max_matches={metareader.max_snippet.max_matches}"
                    f", match_chars={metareader.max_snippet.match_chars}"
                )
            if field.snippet is None:
                # if snippet is not specified, the whole field is requested
                raise HTTPException(
                    status_code=401, detail=f"METAREADER cannot read {field} on index {index}. {max_params_msg}"
                )

            valid_nomatch_chars = field.snippet.nomatch_chars <= metareader.max_snippet.nomatch_chars
            valid_max_matches = field.snippet.max_matches <= metareader.max_snippet.max_matches
            valid_match_chars = field.snippet.match_chars <= metareader.max_snippet.match_chars
            valid = valid_nomatch_chars and valid_max_matches and valid_match_chars
            if not valid:
                raise HTTPException(
                    status_code=401,
                    detail=f"The requested snippet of {field.name} on index {index} is too long. {max_params_msg}",
                )
        else:
            raise HTTPException(
                status_code=401,
                detail=f"METAREADER cannot read {field.name} on index {index}",
            )


def get_allowed_fields(user: User, index: str) -> list[FieldSpec]:
    """
    For any endpoint that returns field values, make sure the user only gets fields that
    they are allowed to see. If fields is None, return all allowed fields. If fields is not None,
    check whether the user can access the fields (If not, raise an error).
    """
    role = get_project_role(user.email, index)
    if not role_is_at_least(role, Role.METAREADER):
        raise HTTPException(
            status_code=403,
            detail=f"User {user.email} does not have permission to access index {index}",
        )
    is_reader = role_is_at_least(role, Role.READER)

    allowed_fields: list[FieldSpec] = []
    for name, field in get_fields(index).items():
        if is_reader:
            allowed_fields.append(FieldSpec(name=name))
        else:
            metareader = field.metareader
            if metareader.access == "read":
                allowed_fields.append(FieldSpec(name=name))
            if metareader.access == "snippet":
                allowed_fields.append(FieldSpec(name=name, snippet=metareader.max_snippet))

    return allowed_fields
