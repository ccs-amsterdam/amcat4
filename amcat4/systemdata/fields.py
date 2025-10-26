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

from _pytest import logging
from elasticsearch import NotFoundError
from elasticsearch.helpers.actions import scan
from fastapi import HTTPException

from amcat4.elastic import es
from amcat4.models import (
    CreateDocumentField,
    ElasticType,
    DocumentField,
    DocumentFieldMetareaderAccess,
    FieldSpec,
    FieldType,
    IndexId,
    Role,
    Roles,
    UpdateDocumentField,
    User,
)
from amcat4.systemdata.roles import get_user_project_role, list_user_project_roles, role_is_at_least
from amcat4.systemdata.versions import fields_index, fields_index_id
from amcat4.elastic.util import BulkInsertAction, es_bulk_upsert, index_scan
from amcat4.systemdata.typemap import TYPEMAP_AMCAT_TO_ES, TYPEMAP_ES_TO_AMCAT


def create_fields(index: str, fields: Mapping[str, FieldType | CreateDocumentField]):
    mapping: dict[str, Any] = {}
    current_fields = list_fields(index)

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
            elastic_type = _get_default_field(settings.type).elastic_type

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

        # if elastic_type in ["object", "nested"]:
        #     mapping[field]["dynamic"] = True

        if settings.type in ["date"]:
            mapping[field]["format"] = "strict_date_optional_time"

        current_fields[field] = DocumentField(
            type=settings.type,
            elastic_type=elastic_type,
            identifier=settings.identifier,
            metareader=settings.metareader or _get_default_metareader(settings.type),
        )
        _check_forbidden_type(current_fields[field], settings.type)

    if new_identifiers:
        # new identifiers are only allowed if the index had identifiers, or if it is a new index (i.e. no documents)
        has_docs = es().count(index=index)["count"] > 0
        if has_docs and not old_identifiers:
            raise ValueError("Cannot add identifiers. Index already has documents with no identifiers.")

    if len(mapping) > 0:
        es().indices.put_mapping(index=index, properties=mapping)
        _update_fields(index, current_fields)


def update_fields(index: str, fields: dict[str, UpdateDocumentField]):
    current_fields = list_fields(index)

    for field, new_settings in fields.items():
        current = current_fields.get(field)
        if current is None:
            raise ValueError(f"Field {field} does not exist")

        if new_settings.type is not None:
            _check_forbidden_type(current, new_settings.type)

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

    _update_fields(index, current_fields)


def list_fields(index: str) -> dict[str, DocumentField]:
    """
    Retrieve the fields settings for this index. Look for both the field settings in the system index,
    and the field mappings in the index itself. If a field is not defined in the system index, return the
    default settings for that field type and add it to the system index. This way, any elastic index can be imported
    """
    fields: dict[str, DocumentField] = {}

    try:
        system_index_fields = _list_fields(index)
    except NotFoundError:
        system_index_fields = {}

    update_system_index = False
    for field, elastic_type in _get_es_index_fields(index):
        type = TYPEMAP_ES_TO_AMCAT.get(elastic_type)

        if type is None:
            logging.warning(f"Field {field} in index {index} has unsupported elastic type {elastic_type}, skipping")
            continue

        if field not in system_index_fields:
            update_system_index = True
            fields[field] = _get_default_field(type)
        else:
            fields[field] = system_index_fields[field]

    if update_system_index:
        _update_fields(index, fields)

    return fields


def allowed_fieldspecs(user: User, indices: list[IndexId]) -> list[FieldSpec]:
    """
    Returns the intersection of allowed fieldspecs across multiple indices for the given user.
    """

    fields_across_indices: dict[str, list[FieldSpec] | None] = {}

    roles = list_user_project_roles(user, project_ids=indices)
    role_dict = {role.project_id: role.role for role in roles}

    # Note that we NEED to use list_fields and not _list_fields,
    # because we need to be certain the es fields are all registered in the system index.
    for index in indices:
        for field_name, field in list_fields(index).items():
            if field_name not in fields_across_indices:
                fields_across_indices[field_name] = []
            role = role_dict.get(index, "NONE")
            fieldspec = get_fieldspec_for_role(role, field)
            fields_across_indices[field_name].append(fieldspec)

    fieldspecs: list[FieldSpec] = []
    for name, specs in fields_across_indices.items():
        fieldspecs.append(intersect_fieldspecs(specs))

    return fieldspecs


def get_fieldspec_for_role(role: Role, field: DocumentField) -> FieldSpec | None:
    if not role_is_at_least(role, Roles.METAREADER):
        return None

    if role_is_at_least(role, Roles.READER):
        return FieldSpec(name=field.name)

    metareader = field.metareader
    if metareader.access == "read":
        return FieldSpec(name=field.name)
    elif metareader.access == "snippet":
        return FieldSpec(name=field.name, snippet=metareader.max_snippet)
    elif metareader.access == "none":
        return None
    else:
        raise ValueError(f"Unknown metareader access type: {metareader.access}")


def intersect_fieldspecs(specs: list[FieldSpec | None]) -> FieldSpec | None:
    min_spec = specs[0]
    if min_spec is None:
        return None
    for spec in specs[1:]:
        if spec is None:
            return None
        if min_spec.name != spec.name:
            raise ValueError(f"Cannot intersect fieldspecs with different names: {min_spec.name} and {spec.name}")

        if spec.snippet is not None:
            if min_spec.snippet is None:
                min_spec.snippet = spec.snippet
            else:
                min_spec.snippet.nomatch_chars = min(min_spec.snippet.nomatch_chars, spec.snippet.nomatch_chars)
                min_spec.snippet.max_matches = min(min_spec.snippet.max_matches, spec.snippet.max_matches)
                min_spec.snippet.match_chars = min(min_spec.snippet.match_chars, spec.snippet.match_chars)

    return min_spec


def HTTPException_if_invalid_field_access(indices: list[str], user: User, fields: list[FieldSpec]) -> None:
    """
    Check for the given field specifications whether the user has required access on all given indices.
    """
    if len(fields) == 0:
        return None

    roles = list_user_project_roles(user, project_ids=indices)
    role_dict = {role.role_context: role for role in roles}

    for index in indices:
        role = role_dict.get(index)
        if not role_is_at_least(role, Roles.METAREADER):
            raise HTTPException(
                status_code=403,
                detail=f"User '{user.email}' does not have permission to access index {index}",
            )
        if role_is_at_least(role, Roles.READER):
            continue

        index_fields = list_fields(index)
        for field in fields:
            if field.name not in index_fields:
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
                        status_code=403, detail=f"METAREADER cannot read {field} on index {index}. {max_params_msg}"
                    )

                valid_nomatch_chars = field.snippet.nomatch_chars <= metareader.max_snippet.nomatch_chars
                valid_max_matches = field.snippet.max_matches <= metareader.max_snippet.max_matches
                valid_match_chars = field.snippet.match_chars <= metareader.max_snippet.match_chars
                valid = valid_nomatch_chars and valid_max_matches and valid_match_chars
                if not valid:
                    raise HTTPException(
                        status_code=403,
                        detail=f"The requested snippet of {field.name} on index {index} is too long. {max_params_msg}",
                    )
            else:
                raise HTTPException(
                    status_code=403,
                    detail=f"METAREADER cannot read {field.name} on index {index}",
                )


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


def create_or_verify_tag_field(index: str | list[str], field: str):
    """
    Create a special type of field that can be used to tag documents.
    Since adding/removing tags supports multiple indices, we first check whether the field name is valid for all indices
    TODO: double check, because this function looks weird
    """
    indices = [index] if isinstance(index, str) else index
    add_to_indices = []
    for i in indices:
        current_fields = list_fields(i)
        if field in current_fields:
            if current_fields[field].type != "tag":
                raise ValueError(f"Field '{field}' already exists in index '{i}' and is not a tag field")
        else:
            add_to_indices.append(i)

    for i in add_to_indices:
        current_fields = list_fields(i)
        current_fields[field] = _get_default_field("tag")
        es().indices.put_mapping(index=index, properties={field: {"type": "keyword"}})
        _update_fields(i, current_fields)


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


def field_stats(index: str, field: str):
    """
    :param index: The index
    :param field: The field name
    :return: A list of values
    """
    aggs = {"facets": {"stats": {"field": field}}}
    r = es().search(index=index, size=0, aggs=aggs)
    return r["aggregations"]["facets"]


def _get_default_metareader(type: FieldType):
    # Safety first: just make "none" the default for everything
    # if [some safe condition that I cant really think of]:
    #     return DocumentFieldMetareaderAccess(access="read")

    return DocumentFieldMetareaderAccess(access="none")


def _get_default_field(type: FieldType):
    """
    Generate a field on the spot with default settings.
    Primary use case is importing existing indices with fields that are not registered in the system index.
    """
    elastic_type = TYPEMAP_AMCAT_TO_ES.get(type)
    if elastic_type is None:
        raise ValueError(
            f"The default elastic type mapping for field type {type} is not defined (if this happens, blame and inform Kasper)"
        )
    return DocumentField(elastic_type=elastic_type[0], type=type, metareader=_get_default_metareader(type))


def _standardize_createfields(fields: Mapping[str, FieldType | CreateDocumentField]) -> dict[str, CreateDocumentField]:
    sfields = {}
    for k, v in fields.items():
        if isinstance(v, str):
            assert v in get_args(FieldType), f"Unknown amcat type {v}"
            sfields[k] = CreateDocumentField(type=cast(FieldType, v))
        else:
            sfields[k] = v
    return sfields


def _check_forbidden_type(field: DocumentField, type: FieldType):
    if field.identifier:
        for forbidden_type in ["tag", "vector"]:
            if type == forbidden_type:
                raise ValueError(f"Field {field} is an identifier field, which cannot be a {forbidden_type} field")


def _update_fields(index: str, fields: dict[str, DocumentField]):
    def insert_fields():
        for field, settings in fields.items():
            id = fields_index_id(index, field)
            field_doc = {"index": index, "name": field, "settings": settings.model_dump()}
            yield BulkInsertAction(index=fields_index(), id=id, doc=field_doc)

    es_bulk_upsert(insert_fields())


def _list_fields(index: str) -> dict[str, DocumentField]:
    docs = index_scan(fields_index(), query={"term": {"index": index}})
    return {doc["name"]: DocumentField.model_validate(doc["settings"]) for id, doc in docs}


def _get_es_index_fields(index: str) -> Iterator[tuple[str, ElasticType]]:
    r = es().indices.get_mapping(index=index)

    if "properties" in r[index]["mappings"]:
        for k, v in r[index]["mappings"]["properties"].items():
            yield k, v.get("type", "object")
