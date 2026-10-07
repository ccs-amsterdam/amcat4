"""
Document fields.

A field has a name (a project-level label), an AmCAT type, and settings such as metareader access.
The values of a field are stored in the documents table under a stable field key (see amcat4.postgres.fields).
"""

import datetime
from typing import Any, Iterable, Mapping, get_args

from fastapi import HTTPException
from psycopg import sql
from psycopg.types.json import Jsonb

from amcat4.errors import NotFoundError
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
from amcat4.postgres.connection import connection, fetch_all, fetch_one
from amcat4.postgres.fields import FieldInfo, FieldSet, field_info_from_row, sort_slot_for_type
from amcat4.postgres.projects import project_pk, project_pks
from amcat4.systemdata.roles import HTTPException_if_not_project_index_role, list_user_project_roles, role_is_at_least
from amcat4.systemdata.typemap import list_allowed_elastic_types

_COLUMNS = "pk, name, type, elastic_type, identifier, metareader, client_settings, sort_slot"


def _document_field(row: dict) -> DocumentField:
    return DocumentField.model_validate({k: row[k] for k in row if k not in ("pk", "name")})


async def delete_all_project_fields(index: str):
    """Delete all field definitions for the given project"""
    async with connection() as conn:
        await conn.execute("DELETE FROM fields WHERE project_pk = (SELECT pk FROM projects WHERE id = %s)", [index])


async def _field_rows(index: str) -> list[dict]:
    pk = await project_pk(index)
    return await fetch_all(f"SELECT {_COLUMNS} FROM fields WHERE project_pk = %s ORDER BY pk", [pk])  # type: ignore[arg-type]


async def list_fields(index: str, auto_repair: bool = True) -> dict[str, DocumentField]:
    """
    Retrieve the fields settings for this index. (auto_repair is not used anymore, kept for compatibility)
    """
    return {row["name"]: _document_field(row) for row in await _field_rows(index)}


async def field_infos(index: str) -> dict[str, FieldInfo]:
    """The storage information of the fields of an index"""
    return {row["name"]: field_info_from_row(row) for row in await _field_rows(index)}


async def get_fieldset(indices: str | list[str], queryable: set[str] | None = None) -> FieldSet:
    """
    Get the fields of one or more indices, for searching. queryable restricts which fields can be used in queries
    and filters (None = all fields).
    """
    indices = [indices] if isinstance(indices, str) else indices
    pks = await project_pks(indices)
    rows = await fetch_all(
        "SELECT project_pk, pk, name, type, identifier, sort_slot FROM fields WHERE project_pk = ANY(%s) ORDER BY pk",
        [list(pks.values())],
    )
    project_fields: dict[int, dict[str, FieldInfo]] = {pk: {} for pk in pks.values()}
    for row in rows:
        project_fields[row["project_pk"]][row["name"]] = field_info_from_row(row)
    return FieldSet(project_fields, queryable=queryable)


async def create_fields(index: str, fields: Mapping[str, FieldType | CreateDocumentField]):
    """
    Create fields that do not exist yet. Existing fields must have the same storage (elastic) type and identifier
    setting; their other settings are not changed. (For example, a scraper might include the field types in every
    upload request.)
    """
    pk = await project_pk(index)
    current = await list_fields(index)
    sfields = _standardize_createfields(fields)
    old_identifiers = any(f.identifier for f in current.values())
    new_fields: dict[str, DocumentField] = {}

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

        existing = current.get(field)
        if existing is not None:
            if existing.elastic_type != settings.elastic_type:
                raise ValueError(f"Field '{field}' already exists with elastic type '{existing.elastic_type}'. ")
            if existing.identifier != bool(settings.identifier):
                raise ValueError(f"Field '{field}' already exists with identifier '{existing.identifier}'. ")
            continue

        new_field = DocumentField(
            type=settings.type,
            elastic_type=settings.elastic_type,
            identifier=settings.identifier or False,
            metareader=settings.metareader or _get_default_metareader(settings.type),
            client_settings=settings.client_settings or {},
        )
        _check_forbidden_type(new_field, settings.type)
        new_fields[field] = new_field

    if not new_fields:
        return

    async with connection() as conn:
        async with conn.transaction():
            if any(f.identifier for f in new_fields.values()):
                # new identifiers are only allowed if the index had identifiers, or if it has no documents yet
                cur = await conn.execute("SELECT EXISTS (SELECT 1 FROM documents WHERE project_pk = %s) AS e", [pk])
                has_docs = (await cur.fetchone())["e"]  # type: ignore[index, call-overload]
                if has_docs and not old_identifiers:
                    raise ValueError("Cannot add identifiers. Index already has documents with no identifiers.")

            cur = await conn.execute("SELECT sort_slot FROM fields WHERE project_pk = %s AND sort_slot IS NOT NULL", [pk])
            used_slots = {row["sort_slot"] for row in await cur.fetchall()}  # type: ignore[index, call-overload]
            for name, f in new_fields.items():
                # The first date field automatically gets the date sort slot
                slot = "date" if f.type == "date" and "date" not in used_slots else None
                if slot:
                    used_slots.add(slot)
                await conn.execute(
                    """INSERT INTO fields (project_pk, name, type, elastic_type, identifier, metareader, client_settings,
                                           sort_slot)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    [
                        pk,
                        name,
                        f.type,
                        f.elastic_type,
                        f.identifier,
                        Jsonb(f.metareader.model_dump(exclude_none=True)),
                        Jsonb(f.client_settings),
                        slot,
                    ],
                )


async def update_fields(index: str, fields: dict[str, UpdateDocumentField]):
    pk = await project_pk(index)
    rows = {row["name"]: row for row in await _field_rows(index)}
    current = {name: _document_field(row) for name, row in rows.items()}

    async with connection() as conn:
        async with conn.transaction():
            for field, new_settings in fields.items():
                existing = current.get(field)
                if existing is None:
                    raise ValueError(f"Field {field} does not exist")

                if new_settings.type is not None:
                    _check_forbidden_type(existing, new_settings.type)
                    valid_es_types = list_allowed_elastic_types(new_settings.type)
                    if existing.elastic_type not in valid_es_types:
                        raise ValueError(
                            f"Field {field} has the elastic type {existing.elastic_type}. A {new_settings.type} "
                            f"field can only have the following elastic types: {valid_es_types}."
                        )
                    existing.type = new_settings.type

                if new_settings.metareader is not None:
                    if existing.type != "text" and new_settings.metareader.access == "snippet":
                        raise ValueError(f"Field {field} is not of type text, cannot set metareader access to snippet")
                    existing.metareader = new_settings.metareader

                if new_settings.client_settings is not None:
                    existing.client_settings = new_settings.client_settings

                await conn.execute(
                    "UPDATE fields SET type = %s, metareader = %s, client_settings = %s WHERE pk = %s",
                    [
                        existing.type,
                        Jsonb(existing.metareader.model_dump(exclude_none=True)),
                        Jsonb(existing.client_settings),
                        rows[field]["pk"],
                    ],
                )

                if new_settings.fast_sort is not None:
                    info = field_info_from_row({**rows[field], "type": existing.type})
                    await _set_sort_slot(conn, pk, info, new_settings.fast_sort)


async def rename_field(index: str, old: str, new: str) -> None:
    """
    Rename a field. This only changes the field definition: values are stored by field key, not by name
    """
    pk = await project_pk(index)
    async with connection() as conn:
        cur = await conn.execute("SELECT 1 FROM fields WHERE project_pk = %s AND name = %s", [pk, new])
        if await cur.fetchone():
            raise ValueError(f"Field {new} already exists")
        cur = await conn.execute("UPDATE fields SET name = %s WHERE project_pk = %s AND name = %s", [new, pk, old])
        if cur.rowcount == 0:
            raise NotFoundError(f"Field {old} does not exist")


async def _set_sort_slot(conn, project: int, f: FieldInfo, fast_sort: bool) -> None:
    """Put a field in its sort slot (or remove it), and copy the values to the sort column"""
    if not fast_sort:
        if f.sort_slot:
            await conn.execute("UPDATE fields SET sort_slot = NULL WHERE pk = %s", [f.pk])
            await conn.execute(
                sql.SQL("UPDATE documents SET {} = NULL WHERE project_pk = %s").format(sql.Identifier(f"sort_{f.sort_slot}")),
                [project],
            )
        return
    slot = sort_slot_for_type(f.type)
    if slot is None:
        raise ValueError(f"Fields of type {f.type} cannot be used for fast sorting")
    if f.sort_slot == slot:
        return
    await conn.execute("UPDATE fields SET sort_slot = NULL WHERE project_pk = %s AND sort_slot = %s", [project, slot])
    await conn.execute("UPDATE fields SET sort_slot = %s WHERE pk = %s", [slot, f.pk])
    cast = {"date": sql.SQL("timestamptz"), "number": sql.SQL("double precision"), "keyword": sql.SQL("text")}[slot]
    await conn.execute(
        sql.SQL("UPDATE documents SET {} = ({}->>{})::{} WHERE project_pk = %s").format(
            sql.Identifier(f"sort_{slot}"), sql.Identifier(f.column), sql.Literal(f.key), cast
        ),
        [project],
    )


async def allowed_fieldspecs(user: User, indices: list[IndexId]) -> list[FieldSpec]:
    """
    Returns the intersection of allowed fieldspecs across multiple indices for the given user.
    """

    fields_across_indices: dict[str, list[FieldSpec | None]] = {}

    roles = await list_user_project_roles(user, project_ids=indices)
    role_dict: dict[str, RoleRule] = {role.role_context: role for role in roles}

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
    docfield = (await list_fields(index)).get(field)
    if docfield is None:
        raise HTTPException(
            status_code=400,
            detail=f"Field '{field}' does not exist in index '{index}'",
        )
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
    if user.auth_disabled:
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
    Coerces values into the respective type
    """
    if type == "date":
        if isinstance(value, datetime.date):
            return value.isoformat()
        str_value = str(value)
        try:
            datetime.datetime.fromisoformat(str_value)
        except ValueError:
            raise ValueError(f"Invalid date value: {value!r}. Dates must be valid ISO 8601 with year between 1 and 9999.")
        return str_value
    if type == "tag" and isinstance(value, Iterable) and not isinstance(value, str):
        return [str(val) for val in value]
    if type in ["text", "tag"]:
        return str(value)
    if type in ["boolean"]:
        return bool(value)
    if type in ["number"]:
        return float(value)
    if type in ["integer"]:
        return int(value)
    if type in ["image", "video", "audio"]:
        return str(value)
    return value


async def create_or_verify_tag_field(index: str | list[str], field: str):
    """
    Make sure the field exists as a tag field in all given indices (creating it where it does not exist)
    """
    indices = [index] if isinstance(index, str) else index
    for i in indices:
        current_fields = await list_fields(i)
        if field in current_fields:
            if current_fields[field].type != "tag":
                raise ValueError(f"Field '{field}' already exists in index '{i}' and is not a tag field")
    for i in indices:
        await create_fields(i, {field: "tag"})


async def _field_expression(index: str, field: str) -> tuple[int, FieldInfo]:
    pk = await project_pk(index)
    f = (await field_infos(index)).get(field)
    if f is None:
        raise NotFoundError(f"Field {field} does not exist in index {index}")
    return pk, f


async def field_values(index: str, field: str, size: int) -> list[str]:
    """
    Get the values for a given field (e.g. to populate list of filter values on keyword field)
    Results are sorted descending by document frequency
    """
    pk, f = await _field_expression(index, field)
    if f.column != "meta_data":
        raise ValueError(f"Cannot list values of {f.type} field {field}")
    value = sql.SQL("documents.meta_data->{}").format(sql.Literal(f.key))
    elements = sql.SQL("CASE jsonb_typeof({v}) WHEN 'array' THEN {v} ELSE jsonb_build_array({v}) END").format(v=value)
    rows = await fetch_all(
        sql.SQL(
            """SELECT value, count(*) AS n FROM documents, jsonb_array_elements_text({}) AS value
               WHERE project_pk = %s AND documents.meta_data ? {} GROUP BY value ORDER BY n DESC, value LIMIT %s"""
        ).format(elements, sql.Literal(f.key)),
        [pk, size],
    )
    return [row["value"] for row in rows]


async def field_stats(index: str, field: str) -> dict[str, Any]:
    """
    Get count, min, max, avg and sum of a numeric or date field
    """
    pk, f = await _field_expression(index, field)
    if f.type not in ("number", "integer", "date"):
        raise ValueError(f"Cannot compute statistics for {f.type} field {field}")
    raw = sql.SQL("(documents.meta_data->>{})").format(sql.Literal(f.key))
    if f.type == "date":
        x = sql.SQL("extract(epoch FROM {}::timestamptz) * 1000").format(raw)
    else:
        x = sql.SQL("{}::double precision").format(raw)
    row = await fetch_one(
        sql.SQL(
            "SELECT count({x}) AS count, min({x}) AS min, max({x}) AS max, avg({x}) AS avg, sum({x}) AS sum "
            "FROM documents WHERE project_pk = %s"
        ).format(x=x),
        [pk],
    )
    assert row is not None
    stats = {k: (float(v) if v is not None and k != "count" else v) for k, v in row.items()}
    if f.type == "date":
        for k in ("min", "max", "avg"):
            if stats[k] is not None:
                stats[f"{k}_as_string"] = datetime.datetime.fromtimestamp(stats[k] / 1000, tz=datetime.UTC).isoformat()
    return stats


def _get_default_metareader(type: FieldType):
    # Safety first: just make "none" the default for everything
    return DocumentFieldMetareaderAccess(access="none")


def _get_default_field(type: FieldType, elastic_type: ElasticType | None = None):
    """
    Generate a field on the spot with default settings.
    """
    if elastic_type is None:
        default_elastic_types = list_allowed_elastic_types(type)
        if len(default_elastic_types) == 0:
            raise ValueError(f"The default storage type for field type {type} is not defined")
        elastic_type = default_elastic_types[0]

    return DocumentField(elastic_type=elastic_type, type=type, metareader=_get_default_metareader(type))


def _standardize_createfields(fields: Mapping[str, FieldType | CreateDocumentField]) -> dict[str, CreateDocumentField]:
    sfields: dict[str, CreateDocumentField] = {}
    for k, v in fields.items():
        if isinstance(v, str):
            assert v in get_args(FieldType), f"Unknown amcat type {v}"
            sfields[k] = CreateDocumentField(type=v)
        else:
            sfields[k] = v
    return sfields


def _check_forbidden_type(field: DocumentField, type: FieldType):
    if field.identifier:
        for forbidden_type in ["tag", "vector"]:
            if type == forbidden_type:
                raise ValueError(f"Field {field} is an identifier field, which cannot be a {forbidden_type} field")
