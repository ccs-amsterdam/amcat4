"""
Document storage for the postgres backend.

Documents are uploaded via COPY into a temporary staging table, followed by a single
INSERT ... SELECT ... ON CONFLICT statement. This is fast and gives us proper upsert/skip semantics.
"""

import hashlib
import json
import uuid
from typing import TYPE_CHECKING, Any, Iterable, Literal

from psycopg import AsyncConnection, sql
from psycopg.types.json import Jsonb

from amcat4.postgres.fields import DATE_DERIVED, FieldInfo, FieldSet, derived_date_values, normalize_value

if TYPE_CHECKING:
    from amcat4.postgres.search import SearchQuery

OnConflict = Literal["update", "replace", "skip", "error"]


def stored_values(f: FieldInfo, value: Any) -> dict[str, Any]:
    """The json key(s) and value(s) to store for a field value (date fields also store derived values)"""
    normalized = normalize_value(value, f.type)
    out = {f.key: normalized}
    if f.type == "date":
        out.update(derived_date_values(f, normalized))
    return out


def stored_keys(f: FieldInfo) -> list[str]:
    keys = [f.key]
    if f.type == "date":
        keys += [f.derived_key(part) for part in DATE_DERIVED]
    return keys


def split_document(document: dict[str, Any], fields: dict[str, FieldInfo]) -> tuple[dict, dict, dict, str | None]:
    """
    Split a {name: value} document into (text_data, meta_data, extra_data) dicts keyed by field key,
    and the value for the sort_date column (the primary date field)
    """
    columns: dict[str, dict[str, Any]] = {"text_data": {}, "meta_data": {}, "extra_data": {}}
    sort_date = None
    for name, value in document.items():
        if name == "_id" or value is None:
            continue
        f = fields.get(name)
        if f is None:
            raise ValueError(f"Field {name!r} is not yet specified")
        values = stored_values(f, value)
        columns[f.column].update(values)
        if f.primary_date:
            sort_date = values[f.key]
    return columns["text_data"], columns["meta_data"], columns["extra_data"], sort_date


def dedup_hash(document: dict[str, Any], fields: dict[str, FieldInfo]) -> bytes | None:
    """Hash of the values of the unique fields (keyed by field key, so renaming a field doesn't change it)"""
    unique = sorted((f for f in fields.values() if f.unique_field), key=lambda f: f.key)
    if not unique:
        return None
    values = {f.key: normalize_value(document.get(f.name), f.type) for f in unique}
    return hashlib.sha224(json.dumps(values, sort_keys=True, default=str).encode("utf-8")).digest()


def join_document(row: dict[str, Any], fields: dict[str, FieldInfo], names: Iterable[str] | None = None) -> dict:
    """Convert a stored row back into a {name: value} dict (only for the given field names)"""
    out: dict[str, Any] = {"_id": row["doc_id"]}
    for name in names if names is not None else fields.keys():
        f = fields[name]
        data = row.get(f.column) or {}
        if f.key in data:
            out[name] = data[f.key]
    return out


_STAGING = """
CREATE TEMP TABLE IF NOT EXISTS staging_documents (
    doc_id text, dedup_hash bytea, text_data jsonb, meta_data jsonb, extra_data jsonb, source jsonb, sort_date timestamptz
) ON COMMIT DELETE ROWS
"""

_CONFLICT = {
    "update": """DO UPDATE SET text_data = documents.text_data || EXCLUDED.text_data,
                              meta_data = documents.meta_data || EXCLUDED.meta_data,
                              extra_data = coalesce(documents.extra_data, '{}') || coalesce(EXCLUDED.extra_data, '{}'),
                              sort_date = coalesce(EXCLUDED.sort_date, documents.sort_date),
                              updated_at = now()""",
    "replace": """DO UPDATE SET text_data = EXCLUDED.text_data, meta_data = EXCLUDED.meta_data,
                               extra_data = EXCLUDED.extra_data, sort_date = EXCLUDED.sort_date, updated_at = now()""",
    "skip": "DO NOTHING",
}


async def upload_documents(
    conn: AsyncConnection,
    project_pk: int,
    documents: list[dict[str, Any]],
    fields: dict[str, FieldInfo],
    on_conflict: OnConflict = "update",
    source: dict | None = None,
) -> int:
    """
    Upload documents to a project. Returns the number of inserted or updated documents.

    If the project has unique fields, duplicates are detected on the hash of those fields. Otherwise documents
    are identified by their _id (a random id is generated if not given).

    on_conflict: update (merge given fields into existing document), replace (overwrite), skip, or error
    """
    has_unique = any(f.unique_field for f in fields.values())
    async with conn.transaction():
        await conn.execute(_STAGING)
        async with conn.cursor().copy(
            "COPY staging_documents (doc_id, dedup_hash, text_data, meta_data, extra_data, source, sort_date) FROM STDIN"
        ) as copy:
            for doc in documents:
                text, meta, extra, sort_date = split_document(doc, fields)
                doc_id = str(doc.get("_id") or uuid.uuid4().hex)
                await copy.write_row(
                    [
                        doc_id,
                        dedup_hash(doc, fields),
                        Jsonb(text),
                        Jsonb(meta),
                        Jsonb(extra) if extra else None,
                        Jsonb(source) if source else None,
                        sort_date,
                    ]
                )
        target = "(project_pk, dedup_hash) WHERE dedup_hash IS NOT NULL" if has_unique else "(project_pk, doc_id)"
        conflict = "" if on_conflict == "error" else f"ON CONFLICT {target} {_CONFLICT[on_conflict]}"
        # a batch can contain duplicates itself, which ON CONFLICT cannot handle, so keep the last one
        key = "dedup_hash" if has_unique else "doc_id"
        cur = await conn.execute(
            f"""INSERT INTO documents (project_pk, doc_id, dedup_hash, text_data, meta_data, extra_data, source, sort_date)
                SELECT DISTINCT ON ({key}) %s, doc_id, dedup_hash, text_data, meta_data, extra_data, source, sort_date
                FROM (SELECT *, row_number() OVER () AS rn FROM staging_documents) s
                ORDER BY {key}, rn DESC
                {conflict}""",  # type: ignore[arg-type]
            [project_pk],
        )
        return cur.rowcount


async def get_document(conn: AsyncConnection, project_pk: int, doc_id: str, fields: dict[str, FieldInfo]) -> dict | None:
    cur = await conn.execute(
        "SELECT doc_id, text_data, meta_data, extra_data FROM documents WHERE project_pk = %s AND doc_id = %s",
        [project_pk, doc_id],
    )
    row = await cur.fetchone()
    return join_document(row, fields) if row else None  # type: ignore[arg-type]


async def delete_document(conn: AsyncConnection, project_pk: int, doc_id: str) -> bool:
    cur = await conn.execute("DELETE FROM documents WHERE project_pk = %s AND doc_id = %s", [project_pk, doc_id])
    return cur.rowcount > 0


async def copy_documents(
    conn: AsyncConnection,
    from_project_pk: int,
    to_project_pk: int,
    field_map: dict[FieldInfo, FieldInfo],
    where_sql: str = "TRUE",
    where_params: list | None = None,
) -> int:
    """
    Physically copy documents (or a subset selected by where_sql) to another project, keeping only the
    fields in field_map (source field -> destination field). Provenance is recorded in the source column.
    """

    for s, d in field_map.items():
        if s.type != d.type:
            raise ValueError(f"Cannot copy {s.name} ({s.type}) to {d.name} ({d.type})")

    def remap(column: str) -> str:
        pairs = [
            (s_key, d_key)
            for s, d in field_map.items()
            if s.column == column
            for s_key, d_key in zip(stored_keys(s), stored_keys(d))
        ]
        if not pairs:
            return "'{}'::jsonb"
        args = ", ".join(f"'{d_key}', {column}->'{s_key}'" for s_key, d_key in pairs)
        return f"jsonb_strip_nulls(jsonb_build_object({args}))"

    primary = [s for s, d in field_map.items() if d.primary_date]
    sort_date = f"(meta_data->>'{primary[0].key}')::timestamptz" if primary else "NULL"

    cur = await conn.execute(
        f"""INSERT INTO documents (project_pk, doc_id, dedup_hash, text_data, meta_data, extra_data, source, sort_date)
            SELECT %s, doc_id, dedup_hash, {remap("text_data")}, {remap("meta_data")}, {remap("extra_data")},
                   jsonb_build_object('project_pk', project_pk, 'doc_id', doc_id), {sort_date}
            FROM documents WHERE project_pk = %s AND ({where_sql})""",  # type: ignore[arg-type]
        [to_project_pk, from_project_pk, *(where_params or [])],
    )
    return cur.rowcount


async def update_tag_by_query(
    conn: AsyncConnection,
    fieldset: FieldSet,
    query: "SearchQuery",
    field: FieldInfo,
    tag: str,
    action: Literal["add", "remove"],
) -> int:
    """Add or remove a tag on all documents matching the query. Returns the number of changed documents."""
    from amcat4.postgres.search import compile_search

    if field.type != "tag":
        raise ValueError(f"Field {field.name} is not a tag field")
    c = compile_search(fieldset, query)
    key = sql.Literal(field.key)
    if action == "add":
        stmt = sql.SQL(
            """UPDATE documents SET meta_data = jsonb_set(meta_data, ARRAY[{key}],
                   coalesce(meta_data->{key}, '[]'::jsonb) || to_jsonb(%s::text)), updated_at = now()
               WHERE {where} AND NOT coalesce(meta_data->{key} ? %s, false)"""
        )
    else:
        stmt = sql.SQL(
            """UPDATE documents SET meta_data = CASE WHEN meta_data->{key} = to_jsonb(ARRAY[%s::text])
                   THEN meta_data - {key} ELSE jsonb_set(meta_data, ARRAY[{key}], (meta_data->{key}) - %s) END,
                   updated_at = now()
               WHERE {where} AND coalesce(meta_data->{key} ? %s, false)"""
        )
    params = [tag, *c.params, tag] if action == "add" else [tag, tag, *c.params, tag]
    cur = await conn.execute(stmt.format(key=key, where=c.where), params)
    return cur.rowcount


async def update_by_query(
    conn: AsyncConnection, fieldset: FieldSet, query: "SearchQuery", field: FieldInfo, value: Any
) -> int:
    """Set (or with value=None: remove) a field on all documents matching the query"""
    from amcat4.postgres.search import compile_search

    c = compile_search(fieldset, query)
    column = sql.Identifier(field.column)
    sort_date = sql.SQL(", sort_date = %s") if field.primary_date else sql.SQL("")
    if value is None:
        stmt = sql.SQL("UPDATE documents SET {col} = {col} - %s::text[]{sort_date}, updated_at = now() WHERE {where}")
        params: list[Any] = [stored_keys(field)]
        if field.primary_date:
            params.append(None)
    else:
        stmt = sql.SQL(
            "UPDATE documents SET {col} = coalesce({col}, '{{}}') || %s{sort_date}, updated_at = now() WHERE {where}"
        )
        values = stored_values(field, value)
        params = [Jsonb(values)]
        if field.primary_date:
            params.append(values[field.key])
    cur = await conn.execute(stmt.format(col=column, sort_date=sort_date, where=c.where), [*params, *c.params])
    return cur.rowcount


async def delete_by_query(conn: AsyncConnection, fieldset: FieldSet, query: "SearchQuery") -> int:
    from amcat4.postgres.search import compile_search

    c = compile_search(fieldset, query)
    cur = await conn.execute(sql.SQL("DELETE FROM documents WHERE {}").format(c.where), c.params)
    return cur.rowcount
