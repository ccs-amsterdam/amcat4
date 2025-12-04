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
from typing import Any, AsyncGenerator, Iterable, Mapping, cast, get_args
from typing_extensions import TypedDict

from elasticsearch import NotFoundError
from fastapi import HTTPException

from amcat4.connections import es
from amcat4.elastic.util import BulkInsertAction, es_bulk_upsert, es_get, index_scan
from amcat4.models import (
    CreateDocumentField,
    DocumentField,
    DocumentFieldMetareaderAccess,
    ElasticType,
    FieldSpec,
    FieldType,
    IndexId,
    RoleRule,
    Roles,
    UpdateDocumentField,
    User,
)
from amcat4.systemdata.roles import HTTPException_if_not_project_index_role, list_user_project_roles, role_is_at_least
from amcat4.systemdata.typemap import infer_field_type, list_allowed_elastic_types
from amcat4.systemdata.versions import fields_index_id, fields_index_name


class UpdateFieldMapping(TypedDict):
    name: str
    type: FieldType
    elastic_type: ElasticType


async def create_fields(index: str, fields: Mapping[str, FieldType | CreateDocumentField]):
    current_fields = await list_fields(index)

    sfields = _standardize_createfields(fields)
    old_identifiers = any(f.identifier for f in current_fields.values())

    # flags to track whether we need to update mapping or identifiers
    update_mapping = False
    new_identifiers = False

    for field, settings in sfields.items():
        if settings.elastic_type is not None:
            allowed_types = list_allowed_elastic_types(settings.type)
            if settings.elastic_type not in allowed_types:
                raise ValueError(
                    f"Field type {settings.type} does not support elastic type {settings.elastic_type}. "
                    f"Allowed types are: {allowed_types}"
                )
        else:
            settings.elastic_type = _get_default_field(settings.type).elastic_type

        current = current_fields.get(field)

        if current is not None:
            # fields can already exist. For example, a scraper might include the field types in every
            # upload request. If a field already exists, we'll ignore the new settings, and we will throw an error
            # if static settings (elastic type, identifier) do not match.
            if current.elastic_type != settings.elastic_type:
                raise ValueError(f"Field '{field}' already exists with elastic type '{current.elastic_type}'. ")
            if current.identifier != bool(settings.identifier):
                raise ValueError(f"Field '{field}' already exists with identifier '{current.identifier}'. ")
            continue

        # if field does not exist, we add it to both the mapping and the system index

        update_mapping = True
        if settings.identifier:
            new_identifiers = True

        new_field = DocumentField(
            type=settings.type,
            elastic_type=settings.elastic_type,
            identifier=settings.identifier or False,
            metareader=settings.metareader or _get_default_metareader(settings.type),
        )
        _check_forbidden_type(new_field, settings.type)

        current_fields[field] = new_field

    if new_identifiers:
        # new identifiers are only allowed if the index had identifiers, or if it is a new index (i.e. no documents)
        has_docs = (await (es()).count(index=index))["count"] > 0
        if has_docs and not old_identifiers:
            raise ValueError("Cannot add identifiers. Index already has documents with no identifiers.")

    if update_mapping:
        await _update_index_fields_mappings(index, current_fields)


async def update_fields(index: str, fields: dict[str, UpdateDocumentField]):
    current_fields = await list_fields(index)

    for field, new_settings in fields.items():
        current = current_fields.get(field)
        if current is None:
            raise ValueError(f"Field {field} does not exist")

        if new_settings.type is not None:
            _check_forbidden_type(current, new_settings.type)

            valid_es_types = list_allowed_elastic_types(new_settings.type)
            if current.elastic_type not in valid_es_types:
                raise ValueError(
                    f"Field {field} has the elastic type {current.elastic_type}. A {new_settings.type} "
                    f"field can only have the following elastic types: {valid_es_types}."
                )
            current_fields[field].type = new_settings.type

        if new_settings.metareader is not None:
            if current.type != "text" and new_settings.metareader.access == "snippet":
                raise ValueError(f"Field {field} is not of type text, cannot set metareader access to snippet")
            current_fields[field].metareader = new_settings.metareader

        if new_settings.client_settings is not None:
            current_fields[field].client_settings = new_settings.client_settings

    await _update_fields(index, current_fields)


async def list_fields(index: str, auto_repair: bool = True) -> dict[str, DocumentField]:
    """
    Retrieve the fields settings for this index.

    If auto_repair is true, look for both (1) the field settings in the 'fields' system index,
    and (2) the field mappings in the index itself. If these are not in sync, fix them.
    """
    if auto_repair:
        return await list_and_repair_fields(index)
    else:
        return await _list_fields(index)


async def list_and_repair_fields(
    index: str,
):
    fields: dict[str, DocumentField] = {}

    try:
        system_index_fields = await _list_fields(index)
    except NotFoundError:
        system_index_fields = {}

    # check if all fields in elastic are registered in the system index, and otherwise add them (update_system_index=True)
    update_system_index = False
    inferred_fields = await _infer_es_index_fields(index)
    for name, inferred_field in inferred_fields.items():
        if name not in system_index_fields:
            update_system_index = True
            fields[name] = inferred_field
        else:
            fields[name] = system_index_fields[name]

            if fields[name].elastic_type != inferred_field.elastic_type:
                ## if for some reason the elastic types in the system index and mapping don't match, update the system index using the
                ## the inferred type (because we can't update the mapping)
                update_system_index = True
                fields[name].elastic_type = inferred_field.elastic_type

                ## If the current amcat type is not allowed for the new elastic type, we also need to update the amcat type
                if fields[name].elastic_type not in list_allowed_elastic_types(fields[name].type):
                    fields[name].type = inferred_field.type

    # check if all fields in the system index have defined mappings in elastic, and otherwise update mapping (update_mapping=True)
    update_mapping = False
    for name in system_index_fields.keys():
        if name not in inferred_fields.keys():
            update_mapping = True

    if update_mapping:
        await _update_index_fields_mappings(index, fields)

    if update_system_index:
        await _update_fields(index, fields)

    return fields


async def allowed_fieldspecs(user: User, indices: list[IndexId]) -> list[FieldSpec]:
    """
    Returns the intersection of allowed fieldspecs across multiple indices for the given user.
    """

    fields_across_indices: dict[str, list[FieldSpec | None]] = {}

    roles = await list_user_project_roles(user, project_ids=indices)
    role_dict: dict[str, RoleRule] = {role.role_context: role for role in roles}

    # Note that we NEED to use list_fields and not _list_fields,
    # because we need to be certain the es fields are all registered in the system index.
    for index in indices:
        for field_name, field in (await list_fields(index)).items():
            if field_name not in fields_across_indices:
                fields_across_indices[field_name] = []
            role = role_dict.get(index)
            fieldspec = get_fieldspec_for_role(user, role, field_name, field)
            fields_across_indices[field_name].append(fieldspec)

    fieldspecs: list[FieldSpec] = []
    for name, specs in fields_across_indices.items():
        spec = intersect_fieldspecs(specs)
        if spec is not None:
            fieldspecs.append(spec)

    return fieldspecs


def get_fieldspec_for_role(user: User, role: RoleRule | None, field_name: str, field: DocumentField) -> FieldSpec | None:
    if not role_is_at_least(user, role, Roles.METAREADER):
        return None

    if role_is_at_least(user, role, Roles.READER):
        return FieldSpec(name=field_name)

    metareader = field.metareader
    if metareader.access == "read":
        return FieldSpec(name=field_name)
    elif metareader.access == "snippet":
        return FieldSpec(name=field_name, snippet=metareader.max_snippet)
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


async def HTTPException_if_invalid_or_unauthorized_multimedia_field(index: str, field: str, user: User) -> None:
    es_field = await es_get(fields_index_name(), fields_index_id(index, field))
    if es_field is None:
        raise HTTPException(
            status_code=400,
            detail=f"Field '{field}' does not exist in index '{index}'",
        )
    docfield = DocumentField.model_validate(es_field["settings"])
    valid_types = ["image", "video", "audio"]
    if docfield.type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Field '{field}' in index '{index}' is of type '{docfield.type}', "
            f"but one of {valid_types} is required for multimedia operations.",
        )

    min_role = Roles.METAREADER if docfield.metareader.access == "read" else Roles.READER
    await HTTPException_if_not_project_index_role(user, index, min_role)


async def HTTPException_if_invalid_field_access(indices: list[str], user: User, fields: list[FieldSpec]) -> None:
    """
    Check for the given field specifications whether the user has required access on all given indices.
    """
    if len(fields) == 0:
        return None

    roles = await list_user_project_roles(user, project_ids=indices)
    role_dict = {role.role_context: role for role in roles}

    for index in indices:
        role = role_dict.get(index)
        if not role_is_at_least(user, role, Roles.METAREADER):
            raise HTTPException(
                status_code=403,
                detail=f"User '{user.email}' does not have permission to access index {index}",
            )
        if role_is_at_least(user, role, Roles.READER):
            continue

        index_fields = await list_fields(index)
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
    if type in ["text", "tag", "date"]:
        return str(value)
    if type in ["boolean"]:
        return bool(value)
    if type in ["number"]:
        return float(value)
    if type in ["integer"]:
        return int(value)

    # TODO: check coercion / validation for object, vector and geo types
    if type in ["object"]:
        return value
    if type in ["vector"]:
        return value
    if type in ["geo_point"]:
        return value

    # TODO: Perhaps we should check if its a local file path (meaning we use S3), and in
    # that case enforce using a correct extension.
    if type in ["image", "video", "audio"]:
        return str(value)

    return value


async def create_or_verify_tag_field(index: str | list[str], field: str):
    """
    Create a special type of field that can be used to tag documents.
    Since adding/removing tags supports multiple indices, we first check whether the field name is valid for all indices
    TODO: double check, because this function looks weird
    """
    indices = [index] if isinstance(index, str) else index
    add_to_indices = []
    for i in indices:
        current_fields = await list_fields(i)
        if field in current_fields:
            if current_fields[field].type != "tag":
                raise ValueError(f"Field '{field}' already exists in index '{i}' and is not a tag field")
        else:
            add_to_indices.append(i)

    for i in add_to_indices:
        current_fields = await list_fields(i)
        current_fields[field] = _get_default_field("tag")
        await (es()).indices.put_mapping(index=index, properties={field: {"type": "keyword"}})
        await _update_fields(i, current_fields)


async def field_values(index: str, field: str, size: int) -> list[str]:
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
    r = await (es()).search(index=index, size=0, aggs=aggs)
    return [x["key"] for x in r["aggregations"]["unique_values"]["buckets"]]


async def field_stats(index: str, field: str):
    """
    :param index: The index
    :param field: The field name
    :return: A list of values
    """
    aggs = {"facets": {"stats": {"field": field}}}
    r = await (es()).search(index=index, size=0, aggs=aggs)
    return r["aggregations"]["facets"]


def _get_default_metareader(type: FieldType):
    # Safety first: just make "none" the default for everything
    # if [some safe condition that I cant really think of]:
    #     return DocumentFieldMetareaderAccess(access="read")

    return DocumentFieldMetareaderAccess(access="none")


def _get_default_field(type: FieldType, elastic_type: ElasticType | None = None):
    """
    Generate a field on the spot with default settings.
    Primary use case is importing existing indices with fields that are not registered in the system index.
    """
    if elastic_type is None:
        default_elastic_types = list_allowed_elastic_types(type)

        if len(default_elastic_types) == 0:
            raise ValueError(
                f"The default elastic type mapping for field type {type} is not defined (if this happens, blame and inform Kasper)"
            )
        elastic_type = default_elastic_types[0]

    return DocumentField(elastic_type=elastic_type, type=type, metareader=_get_default_metareader(type))


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


async def _update_fields(index: str, fields: dict[str, DocumentField]):
    async def insert_fields() -> AsyncGenerator[BulkInsertAction, None]:
        for field, settings in fields.items():
            id = fields_index_id(index, field)
            field_doc = {"index": index, "name": field, "settings": settings.model_dump()}
            yield BulkInsertAction(index=fields_index_name(), id=id, doc=field_doc)

    await es_bulk_upsert(insert_fields())


async def _list_fields(index: str) -> dict[str, DocumentField]:
    docs = index_scan(fields_index_name(), query={"term": {"index": index}})
    return {doc["name"]: DocumentField.model_validate(doc["settings"]) async for id, doc in docs}


async def _get_es_index_fields(index: str) -> AsyncGenerator[tuple[str, dict], None]:
    r = await (es()).indices.get_mapping(index=index)
    if "properties" in r[index]["mappings"]:
        for name, mapping in r[index]["mappings"]["properties"].items():
            yield name, mapping


async def _infer_es_index_fields(index: str) -> dict[str, DocumentField]:
    fields: dict[str, DocumentField] = {}
    async for name, mapping in _get_es_index_fields(index):
        elastic_type = mapping.get("type", "object")
        nested_props = mapping.get("properties", None)
        type = infer_field_type(elastic_type, nested_props)
        field = _get_default_field(type, elastic_type)
        fields[name] = field
    return fields


async def _update_index_fields_mappings(index: str, fields: dict[str, DocumentField]) -> None:
    """
    Update the elasticsearch index mapping for the given fields.
    Note that we can only add new fields or change certain properties of existing fields.
    We cannot change the type of an existing field.
    """
    mapping_updates: dict[str, dict[str, Any]] = {}
    for field_name, field in fields.items():
        mapping_updates[field_name] = {"type": field.elastic_type}

        ## Date fields need a specific format
        if field.type == "date":
            mapping_updates[field_name]["format"] = "strict_date_optional_time"

    await (es()).indices.put_mapping(index=index, properties=mapping_updates)
    await _update_fields(index, fields)
