"""
Document storage for the postgres backend.

Documents are uploaded via COPY into a temporary staging table, followed by a single
INSERT ... SELECT ... ON CONFLICT statement. This is fast and gives us proper upsert/skip semantics.
"""

import hashlib
import json
import uuid
from typing import Any, Iterable, Literal

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from amcat4.postgres.fields import FieldInfo, normalize_value

OnConflict = Literal["update", "replace", "skip", "error"]


def split_document(document: dict[str, Any], fields: dict[str, FieldInfo]) -> tuple[dict, dict, dict]:
    """Split a {name: value} document into (text_data, meta_data, extra_data) dicts keyed by field key"""
    text: dict[str, Any] = {}
    meta: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    for name, value in document.items():
        if name == "_id" or value is None:
            continue
        f = fields.get(name)
        if f is None:
            raise ValueError(f"Field {name!r} is not yet specified")
        {"text_data": text, "meta_data": meta, "extra_data": extra}[f.column][f.key] = normalize_value(value, f.type)
    return text, meta, extra


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
    doc_id text, dedup_hash bytea, text_data jsonb, meta_data jsonb, extra_data jsonb, source jsonb
) ON COMMIT DELETE ROWS
"""

_CONFLICT = {
    "update": """DO UPDATE SET text_data = documents.text_data || EXCLUDED.text_data,
                              meta_data = documents.meta_data || EXCLUDED.meta_data,
                              extra_data = coalesce(documents.extra_data, '{}') || coalesce(EXCLUDED.extra_data, '{}'),
                              updated_at = now()""",
    "replace": """DO UPDATE SET text_data = EXCLUDED.text_data, meta_data = EXCLUDED.meta_data,
                               extra_data = EXCLUDED.extra_data, updated_at = now()""",
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
            "COPY staging_documents (doc_id, dedup_hash, text_data, meta_data, extra_data, source) FROM STDIN"
        ) as copy:
            for doc in documents:
                text, meta, extra = split_document(doc, fields)
                doc_id = str(doc.get("_id") or uuid.uuid4().hex)
                await copy.write_row(
                    [
                        doc_id,
                        dedup_hash(doc, fields),
                        Jsonb(text),
                        Jsonb(meta),
                        Jsonb(extra) if extra else None,
                        Jsonb(source) if source else None,
                    ]
                )
        target = "(project_pk, dedup_hash) WHERE dedup_hash IS NOT NULL" if has_unique else "(project_pk, doc_id)"
        conflict = "" if on_conflict == "error" else f"ON CONFLICT {target} {_CONFLICT[on_conflict]}"
        # a batch can contain duplicates itself, which ON CONFLICT cannot handle, so keep the last one
        key = "dedup_hash" if has_unique else "doc_id"
        cur = await conn.execute(
            f"""INSERT INTO documents (project_pk, doc_id, dedup_hash, text_data, meta_data, extra_data, source)
                SELECT DISTINCT ON ({key}) %s, doc_id, dedup_hash, text_data, meta_data, extra_data, source
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

    def remap(column: str) -> str:
        pairs = [(s, d) for s, d in field_map.items() if s.column == column]
        if not pairs:
            return "'{}'::jsonb"
        args = ", ".join(f"'{d.key}', {column}->'{s.key}'" for s, d in pairs)
        return f"jsonb_strip_nulls(jsonb_build_object({args}))"

    cur = await conn.execute(
        f"""INSERT INTO documents (project_pk, doc_id, dedup_hash, text_data, meta_data, extra_data, source)
            SELECT %s, doc_id, dedup_hash, {remap("text_data")}, {remap("meta_data")}, {remap("extra_data")},
                   jsonb_build_object('project_pk', project_pk, 'doc_id', doc_id)
            FROM documents WHERE project_pk = %s AND ({where_sql})""",  # type: ignore[arg-type]
        [to_project_pk, from_project_pk, *(where_params or [])],
    )
    return cur.rowcount
