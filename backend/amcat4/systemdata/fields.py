"""
Document fields.

A field has a name (a project-level label), an AmCAT type, and settings such as who can see and query it.
The values of a field are stored in the documents table under a stable field key (see amcat4.postgres.fields).
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Mapping, get_args

from fastapi import HTTPException
from psycopg import sql
from psycopg.types.json import Jsonb

from amcat4.errors import NotFoundError
from amcat4.models import (
    CreateDocumentField,
    DocumentField,
    FieldSpec,
    FieldType,
    IndexId,
    RoleRule,
    Roles,
    SnippetParams,
    UpdateDocumentField,
    User,
)
from amcat4.postgres.connection import connection, fetch_all
from amcat4.postgres.documents import convert_field, delete_field_values, update_dedup_hashes
from amcat4.postgres.fields import FieldInfo, FieldSet, field_info_from_row, sort_slot_for_type, storage_column
from amcat4.postgres.layout import project_filter
from amcat4.postgres.projects import project_partitions, project_pk, project_pks
from amcat4.systemdata.roles import get_user_project_role, role_is_at_least

_COLUMNS = "pk, name, type, unique_field, metareader, reader, client_settings, sort_slot"


def _document_field(row: dict) -> DocumentField:
    return DocumentField(
        type=row["type"],
        unique=row["unique_field"],
        metareader=row["metareader"],
        reader=row["reader"],
        client_settings=row["client_settings"],
        sort_slot=row["sort_slot"],
    )


async def delete_all_project_fields(index: str):
    """Delete all field definitions for the given project"""
    async with connection() as conn:
        await conn.execute("DELETE FROM fields WHERE project_pk = (SELECT pk FROM projects WHERE id = %s)", [index])


async def delete_fields(index: str, names: list[str]) -> None:
    """Delete fields and their values from all documents of the project"""
    pk = await project_pk(index)
    infos = await field_infos(index)
    missing = [n for n in names if n not in infos]
    if missing:
        raise NotFoundError(f"Fields do not exist: {', '.join(missing)}")
    async with connection() as conn, conn.transaction():
        for name in names:
            await delete_field_values(conn, pk, infos[name])
            await conn.execute("DELETE FROM fields WHERE pk = %s", [infos[name].pk])
        if any(infos[n].unique for n in names):
            await update_dedup_hashes(conn, pk, {n: f for n, f in infos.items() if n not in names})


async def _field_rows(index: str) -> list[dict]:
    pk = await project_pk(index)
    return await fetch_all(f"SELECT {_COLUMNS} FROM fields WHERE project_pk = %s ORDER BY pk", [pk])  # type: ignore[arg-type]


async def list_fields(index: str) -> dict[str, DocumentField]:
    """Retrieve the field settings for this index"""
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
        "SELECT project_pk, pk, name, type, unique_field, sort_slot FROM fields WHERE project_pk = ANY(%s) ORDER BY pk",
        [list(pks.values())],
    )
    project_fields: dict[int, dict[str, FieldInfo]] = {pk: {} for pk in pks.values()}
    for row in rows:
        project_fields[row["project_pk"]][row["name"]] = field_info_from_row(row)
    return FieldSet(project_fields, queryable=queryable, partitions=await project_partitions(list(pks.values())))


def _standardize_createfields(fields: Mapping[str, FieldType | CreateDocumentField]) -> dict[str, CreateDocumentField]:
    sfields: dict[str, CreateDocumentField] = {}
    for k, v in fields.items():
        if isinstance(v, str):
            if v not in get_args(FieldType):
                raise ValueError(f"Unknown field type {v}")
            sfields[k] = CreateDocumentField(type=v)
        else:
            sfields[k] = v
    return sfields


async def create_fields(index: str, fields: Mapping[str, FieldType | CreateDocumentField]):
    """
    Create fields that do not exist yet. Existing fields must have the same type; their other settings are not changed.
    (For example, a scraper might include the field types in every upload request.)
    Use update_fields to change existing fields.
    """
    pk = await project_pk(index)
    current = await list_fields(index)
    new_fields: dict[str, DocumentField] = {}

    for name, settings in _standardize_createfields(fields).items():
        existing = current.get(name)
        if existing is not None:
            if existing.type != settings.type:
                raise ValueError(f"Field '{name}' already exists with type '{existing.type}'")
            continue
        args: dict[str, Any] = dict(type=settings.type, unique=bool(settings.unique))
        for key in ["metareader", "reader", "client_settings"]:
            if getattr(settings, key) is not None:
                args[key] = getattr(settings, key)
        new_fields[name] = DocumentField(**args)

    if not new_fields:
        return

    async with connection() as conn:
        async with conn.transaction():
            cur = await conn.execute("SELECT sort_slot FROM fields WHERE project_pk = %s AND sort_slot IS NOT NULL", [pk])
            used_slots = {row["sort_slot"] for row in await cur.fetchall()}  # type: ignore[index, call-overload]
            for name, f in new_fields.items():
                # The first date field, and a keyword field called source, automatically get the standard columns
                slot = sort_slot_for_type(f.type)
                if slot is None or slot in used_slots or (slot == "source" and name.lower() != "source"):
                    slot = None
                if slot:
                    used_slots.add(slot)
                await conn.execute(
                    """INSERT INTO fields (project_pk, name, type, unique_field, metareader, reader, client_settings,
                                           sort_slot)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    [
                        pk,
                        name,
                        f.type,
                        f.unique,
                        Jsonb(f.metareader.model_dump(exclude_none=True)),
                        Jsonb(f.reader.model_dump(exclude_none=True)),
                        Jsonb(f.client_settings),
                        slot,
                    ],
                )
            if any(f.unique for f in new_fields.values()):
                # existing documents get a hash for the new unique fields (error if there are duplicates)
                cur = await conn.execute(f"SELECT {_COLUMNS} FROM fields WHERE project_pk = %s", [pk])  # type: ignore[arg-type]
                infos = {r["name"]: field_info_from_row(r) for r in await cur.fetchall()}  # type: ignore[index, call-overload]
                await update_dedup_hashes(conn, pk, infos)


async def update_fields(index: str, fields: dict[str, UpdateDocumentField]):
    """
    Update field settings. Changing the type converts the existing values (or raises an error, changing nothing).
    """
    pk = await project_pk(index)
    rows = {row["name"]: row for row in await _field_rows(index)}

    async with connection() as conn:
        async with conn.transaction():
            recompute_unique = False
            for name, update in fields.items():
                row = rows.get(name)
                if row is None:
                    raise ValueError(f"Field {name} does not exist")
                current = _document_field(row)
                info = field_info_from_row(row)
                settings = current.model_dump()

                if update.type is not None and update.type != current.type:
                    storage_column(update.type)  # validates the type
                    new_info = FieldInfo(pk=info.pk, name=info.name, type=update.type, unique=info.unique)
                    await convert_field(conn, pk, info, new_info)
                    settings["type"] = update.type
                    if info.sort_slot and sort_slot_for_type(update.type) != info.sort_slot:
                        await _set_sort_slot(conn, pk, info, False)
                        settings["sort_slot"] = None
                    info = FieldInfo(
                        pk=info.pk, name=info.name, type=update.type, unique=info.unique, sort_slot=settings["sort_slot"]
                    )
                    recompute_unique = recompute_unique or info.unique
                if update.unique is not None and update.unique != current.unique:
                    settings["unique"] = update.unique
                    recompute_unique = True
                for key in ["metareader", "reader", "client_settings"]:
                    if getattr(update, key) is not None:
                        value = getattr(update, key)
                        settings[key] = value.model_dump() if hasattr(value, "model_dump") else value
                new = DocumentField.model_validate(settings)  # validates the combination of settings

                await conn.execute(
                    """UPDATE fields SET type = %s, unique_field = %s, metareader = %s, reader = %s, client_settings = %s
                       WHERE pk = %s""",
                    [
                        new.type,
                        new.unique,
                        Jsonb(new.metareader.model_dump(exclude_none=True)),
                        Jsonb(new.reader.model_dump(exclude_none=True)),
                        Jsonb(new.client_settings),
                        info.pk,
                    ],
                )
                if update.fast_sort is not None:
                    await _set_sort_slot(
                        conn, pk, FieldInfo(pk=info.pk, name=name, type=new.type, sort_slot=info.sort_slot), update.fast_sort
                    )
                if update.name is not None and update.name != name:
                    await _rename_field(conn, pk, name, update.name)

            if recompute_unique:
                cur = await conn.execute(f"SELECT {_COLUMNS} FROM fields WHERE project_pk = %s", [pk])  # type: ignore[arg-type]
                infos = {r["name"]: field_info_from_row(r) for r in await cur.fetchall()}  # type: ignore[index, call-overload]
                await update_dedup_hashes(conn, pk, infos)


async def rename_field(index: str, old: str, new: str) -> None:
    """
    Rename a field. This only changes the field definition: values are stored by field key, not by name
    """
    pk = await project_pk(index)
    async with connection() as conn:
        await _rename_field(conn, pk, old, new)


async def _rename_field(conn, pk: int, old: str, new: str) -> None:
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
                sql.SQL("UPDATE documents SET {} = NULL WHERE {}").format(
                    sql.Identifier(f.sort_slot), await project_filter(conn, project)
                )
            )
        return
    slot = sort_slot_for_type(f.type)
    if slot is None:
        raise ValueError(f"Fields of type {f.type} cannot be used for fast sorting")
    if f.sort_slot == slot:
        return
    await conn.execute("UPDATE fields SET sort_slot = NULL WHERE project_pk = %s AND sort_slot = %s", [project, slot])
    await conn.execute("UPDATE fields SET sort_slot = %s WHERE pk = %s", [slot, f.pk])
    cast = {"date": sql.SQL("timestamptz"), "source": sql.SQL("text")}[slot]
    where = await project_filter(conn, project)
    await conn.execute(
        sql.SQL("UPDATE documents SET {} = ({}->>{})::{} WHERE {}").format(
            sql.Identifier(slot), sql.Identifier(f.column), sql.Literal(f.key), cast, where
        )
    )


###################### FIELD ACCESS ######################


@dataclass
class FieldAccess:
    """What a user can do with the fields of one or more projects"""

    # field name -> FieldSpec (with snippet parameters if the user can only see snippets)
    visible: dict[str, FieldSpec] = field(default_factory=dict)
    queryable: set[str] = field(default_factory=set)


def _field_access_for_role(user: User, role: RoleRule | None, name: str, f: DocumentField) -> tuple[FieldSpec | None, bool]:
    """Returns (FieldSpec if the field is visible, whether it is queryable) for a user with this role"""
    if role_is_at_least(user, role, Roles.WRITER):
        return FieldSpec(name=name), True
    if role_is_at_least(user, role, Roles.READER):
        return (FieldSpec(name=name) if f.reader.visible else None), f.reader.can_query
    if role_is_at_least(user, role, Roles.METAREADER):
        match f.metareader.access:
            case "read":
                spec = FieldSpec(name=name)
            case "snippet":
                spec = FieldSpec(name=name, snippet=f.metareader.max_snippet or SnippetParams())
            case _:
                spec = None
        return spec, f.metareader.can_query
    return None, False


async def field_access(user: User, indices: list[IndexId]) -> FieldAccess:
    """
    Which fields the user can see and query on all given indices. If a field exists in multiple indices, the most
    restrictive settings are used.
    """
    specs: dict[str, list[FieldSpec | None]] = {}
    queryable: dict[str, bool] = {}
    for index in indices:
        role = await get_user_project_role(user, index)
        if not role_is_at_least(user, role, Roles.METAREADER):
            raise HTTPException(403, f"User {user.email or 'GUEST'} does not have permission to access index {index}")
        for name, f in (await list_fields(index)).items():
            spec, can_query = _field_access_for_role(user, role, name, f)
            specs.setdefault(name, []).append(spec)
            queryable[name] = queryable.get(name, True) and can_query
    access = FieldAccess()
    for name, s in specs.items():
        spec = intersect_fieldspecs(s)
        if spec is not None:
            access.visible[name] = spec
    access.queryable = {name for name, q in queryable.items() if q}
    return access


async def allowed_fieldspecs(user: User, indices: list[IndexId]) -> list[FieldSpec]:
    """The fields (and snippets) the user can see on all given indices"""
    return list((await field_access(user, indices)).visible.values())


def intersect_fieldspecs(specs: list[FieldSpec | None]) -> FieldSpec | None:
    min_spec = specs[0]
    if min_spec is None:
        return None
    min_spec = min_spec.model_copy(deep=True)
    for spec in specs[1:]:
        if spec is None:
            return None
        if spec.snippet is not None:
            if min_spec.snippet is None:
                min_spec.snippet = spec.snippet
            else:
                min_spec.snippet.nomatch_words = min(min_spec.snippet.nomatch_words, spec.snippet.nomatch_words)
                min_spec.snippet.max_matches = min(min_spec.snippet.max_matches, spec.snippet.max_matches)
                min_spec.snippet.words_per_match = min(min_spec.snippet.words_per_match, spec.snippet.words_per_match)
    return min_spec


async def HTTPException_if_invalid_field_access(indices: list[str], user: User, fields: list[FieldSpec]) -> None:
    """
    Check whether the user can see the requested fields (or snippets) on all given indices.
    """
    if not fields or user.auth_disabled:
        return
    access = await field_access(user, indices)
    for f in fields:
        allowed = access.visible.get(f.name)
        if allowed is None:
            if any([f.name in await list_fields(ix) for ix in indices]):
                raise HTTPException(403, f"{user.email or 'GUEST'} cannot see field {f.name} on {', '.join(indices)}")
            continue  # field does not exist (in any index), nothing to see
        if allowed.snippet is None:
            continue
        max_snippet = allowed.snippet
        msg = (
            f"You can only see snippets of {f.name}, with at most nomatch_words={max_snippet.nomatch_words}, "
            f"max_matches={max_snippet.max_matches}, words_per_match={max_snippet.words_per_match}"
        )
        if f.snippet is None:
            raise HTTPException(403, msg)
        if (
            f.snippet.nomatch_words > max_snippet.nomatch_words
            or f.snippet.max_matches > max_snippet.max_matches
            or f.snippet.words_per_match > max_snippet.words_per_match
        ):
            raise HTTPException(403, msg)


async def HTTPException_if_invalid_or_unauthorized_multimedia_field(index: str, field: str, user: User) -> None:
    docfield = (await list_fields(index)).get(field)
    if docfield is None:
        raise HTTPException(status_code=400, detail=f"Field '{field}' does not exist in index '{index}'")
    valid_types = ["image", "video", "audio"]
    if docfield.type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Field '{field}' in index '{index}' is of type '{docfield.type}', "
            f"but one of {valid_types} is required for multimedia operations.",
        )
    access = await field_access(user, [index])
    spec = access.visible.get(field)
    if spec is None or spec.snippet is not None:
        raise HTTPException(403, f"{user.email or 'GUEST'} cannot access field {field} on index {index}")


###################### OTHER ######################


async def create_or_verify_tag_field(index: str | list[str], field: str):
    """
    Make sure the field exists as a tag field in all given indices (creating it where it does not exist)
    """
    indices = [index] if isinstance(index, str) else index
    for i in indices:
        current_fields = await list_fields(i)
        if field in current_fields and current_fields[field].type != "tag":
            raise ValueError(f"Field '{field}' already exists in index '{i}' and is not a tag field")
    for i in indices:
        await create_fields(i, {field: "tag"})


async def _field_info(index: str, field: str) -> tuple[int, FieldInfo]:
    pk = await project_pk(index)
    f = (await field_infos(index)).get(field)
    if f is None:
        raise NotFoundError(f"Field {field} does not exist in index {index}")
    return pk, f


async def field_values(index: str, field: str, size: int) -> list[str]:
    """
    Get the most frequent values for a given field (e.g. to populate list of filter values on keyword field)
    """
    pk, f = await _field_info(index, field)
    if f.column != "exact_fields":
        raise ValueError(f"Cannot list values of {f.type} field {field}")
    value = sql.SQL("documents.exact_fields->{}").format(sql.Literal(f.key))
    elements = sql.SQL("CASE jsonb_typeof({v}) WHEN 'array' THEN {v} ELSE jsonb_build_array({v}) END").format(v=value)
    async with connection() as conn:
        cur = await conn.execute(
            sql.SQL(
                """SELECT value, count(*) AS n FROM documents, jsonb_array_elements_text({}) AS value
                   WHERE {} AND documents.exact_fields ? {} GROUP BY value ORDER BY n DESC, value LIMIT %s"""
            ).format(elements, await project_filter(conn, pk), sql.Literal(f.key)),
            [size],
        )
        rows: list[dict] = await cur.fetchall()  # type: ignore[assignment]
    return [row["value"] for row in rows]


async def field_stats(index: str, field: str) -> dict[str, Any]:
    """
    Get the number of documents with a value, and the minimum, maximum and average value of a numeric or date field.
    (For dates, min/max/avg are ISO timestamps)
    """
    pk, f = await _field_info(index, field)
    if f.type not in ("number", "integer", "date"):
        raise ValueError(f"Cannot compute statistics for {f.type} field {field}")
    raw = sql.SQL("(documents.exact_fields->>{})").format(sql.Literal(f.key))
    if f.type == "date":
        x = sql.SQL("extract(epoch FROM {}::timestamptz)").format(raw)
    else:
        x = sql.SQL("{}::double precision").format(raw)
    async with connection() as conn:
        cur = await conn.execute(
            sql.SQL(
                "SELECT count({x}) AS count, min({x}) AS min, max({x}) AS max, avg({x}) AS avg FROM documents WHERE {project}"
            ).format(x=x, project=await project_filter(conn, pk))
        )
        row: dict | None = await cur.fetchone()  # type: ignore[assignment]
    assert row is not None
    stats: dict[str, Any] = {"count": row["count"]}
    for k in ("min", "max", "avg"):
        v = row[k]
        if v is not None and f.type == "date":
            v = datetime.fromtimestamp(float(v), tz=UTC).isoformat()
        elif v is not None:
            v = float(v)
        stats[k] = v
    return stats
