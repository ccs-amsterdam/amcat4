"""
Document storage.

Documents are uploaded via COPY into a temporary staging table, followed by a single INSERT/UPDATE statement.
This is fast and gives us proper create / replace / update / upsert semantics.
"""

import json
import re
import uuid
from typing import TYPE_CHECKING, Any, Iterable, Literal, Sequence

from psycopg import AsyncConnection, sql
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from amcat4.postgres.fields import DATE_DERIVED, FieldInfo, FieldSet, derived_date_values, normalize_value

if TYPE_CHECKING:
    from amcat4.postgres.search import SearchQuery

# index: create or replace; create: only create new documents; update: update existing documents (merge fields);
# upsert: update or create
# create: only create new documents (error if a document already exists)
# update: update existing documents, keeping fields that are not given (error if a document does not exist)
# upsert: update existing documents (keeping fields that are not given), or create new documents
# replace: replace existing documents completely (fields that are not given are removed), or create new documents
OpType = Literal["create", "update", "upsert", "replace"]

SORT_COLUMNS = ["sort_date", "sort_number", "sort_keyword"]


class UploadError(ValueError):
    """An upload could not be completed (nothing was saved)"""


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


class SplitDocument:
    """A document split into the values for the different storage columns"""

    def __init__(self, document: dict[str, Any], fields: dict[str, FieldInfo]):
        self.columns: dict[str, dict[str, Any]] = {"text_data": {}, "meta_data": {}, "extra_data": {}}
        self.sort: dict[str, Any] = {c: None for c in SORT_COLUMNS}
        self.vectors: dict[int, list[float]] = {}
        for name, value in document.items():
            if name == "_id":
                continue
            f = fields.get(name)
            if f is None:
                raise ValueError(f"Field '{name}' is not yet specified")
            if value is None:
                continue
            try:
                if f.column == "vector":
                    self.vectors[f.pk] = normalize_value(value, f.type)
                    continue
                values = stored_values(f, value)
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid value for field '{name}' ({f.type}): {e}") from e
            self.columns[f.column].update(values)
            if f.sort_column:
                self.sort[f.sort_column] = values[f.key]


def dedup_expression(unique_fields: list[FieldInfo], table: str = "documents") -> sql.Composable:
    """
    SQL expression for the deduplication hash: the md5 of the (normalized) values of the unique fields.
    Computed in SQL, so it is identical for new and existing documents.
    """
    values = sql.SQL(", ").join(
        sql.SQL("{}.{}->{}").format(sql.Identifier(table), sql.Identifier(f.column), sql.Literal(f.key))
        for f in sorted(unique_fields, key=lambda f: f.pk)
    )
    return sql.SQL("md5(jsonb_build_array({})::text)").format(values)


async def update_dedup_hashes(
    conn: AsyncConnection, project_pk: int, fields: dict[str, FieldInfo], ids: list[int] | None = None
):
    """
    (Re)compute the deduplication hashes of documents (all documents of the project, or the given internal ids).
    Raises UploadError if this would create duplicate documents.
    """
    unique = [f for f in fields.values() if f.unique]
    expr = dedup_expression(unique) if unique else sql.SQL("NULL")
    where = sql.SQL("project_pk = %s")
    params: list[Any] = [project_pk]
    if ids is not None:
        where = sql.SQL("{} AND id = ANY(%s)").format(where)
        params.append(ids)
    try:
        async with conn.transaction():
            await conn.execute(sql.SQL("UPDATE documents SET dedup_hash = {} WHERE {}").format(expr, where), params)
    except UniqueViolation:
        names = ", ".join(f.name for f in unique)
        raise UploadError(f"This would create multiple documents with the same values for the unique fields ({names})")


def join_document(row: dict[str, Any], fields: dict[str, FieldInfo], names: Iterable[str] | None = None) -> dict:
    """Convert a stored row back into a {name: value} dict (only for the given field names)"""
    out: dict[str, Any] = {"_id": row["doc_id"]}
    for name in names if names is not None else fields.keys():
        f = fields.get(name)
        if f is None:
            continue
        if f.column == "vector":
            value = row.get(f.key)
        else:
            value = (row.get(f.column) or {}).get(f.key)
        if value is not None:
            out[name] = value
    return out


_STAGING = """
CREATE TEMP TABLE IF NOT EXISTS staging_documents (
    rn integer, doc_id text, new_doc_id text, dedup_hash text, target_id bigint, target_doc_id text,
    text_data jsonb, meta_data jsonb, extra_data jsonb, source jsonb,
    sort_date timestamptz, sort_number double precision, sort_keyword text
) ON COMMIT DELETE ROWS
"""

_INSERT_COLUMNS = "project_pk, doc_id, text_data, meta_data, extra_data, source, sort_date, sort_number, sort_keyword"

_MERGE = """text_data = documents.text_data || s.text_data,
            meta_data = documents.meta_data || s.meta_data,
            extra_data = coalesce(documents.extra_data, '{}') || coalesce(s.extra_data, '{}'),
            sort_date = coalesce(s.sort_date, documents.sort_date),
            sort_number = coalesce(s.sort_number, documents.sort_number),
            sort_keyword = coalesce(s.sort_keyword, documents.sort_keyword),
            updated_at = now()"""

_REPLACE = """text_data = s.text_data, meta_data = s.meta_data, extra_data = s.extra_data,
              sort_date = s.sort_date, sort_number = s.sort_number, sort_keyword = s.sort_keyword,
              updated_at = now()"""


def _examples(rows: Sequence[Any], key: str = "doc_id") -> str:
    ids = [str(r[key]) for r in rows[:5]]
    return ", ".join(ids) + (f" (and {len(rows) - 5} more)" if len(rows) > 5 else "")


async def upload_documents(
    conn: AsyncConnection,
    project_pk: int,
    documents: list[dict[str, Any]],
    fields: dict[str, FieldInfo],
    op_type: OpType = "replace",
    source: dict | None = None,
) -> dict[str, int]:
    """
    Upload documents to a project, in a single transaction: either all documents are saved, or none (UploadError).

    Documents are identified by their _id, or (if the project has unique fields) by the values of the unique fields.
    New documents without _id get a random id.
    Returns {"created": n, "updated": n}
    """
    split = [SplitDocument(doc, fields) for doc in documents]
    ids = [str(doc["_id"]) if doc.get("_id") is not None else None for doc in documents]
    unique = [f for f in fields.values() if f.unique]

    async with conn.transaction():
        await conn.execute(_STAGING)
        async with conn.cursor().copy(
            "COPY staging_documents (rn, doc_id, new_doc_id, text_data, meta_data, extra_data, source, sort_date, "
            "sort_number, sort_keyword) FROM STDIN"
        ) as copy:
            for rn, (doc_id, d) in enumerate(zip(ids, split)):
                extra = d.columns["extra_data"]
                await copy.write_row(
                    [
                        rn,
                        doc_id,
                        uuid.uuid4().hex,
                        Jsonb(d.columns["text_data"]),
                        Jsonb(d.columns["meta_data"]),
                        Jsonb(extra) if extra else None,
                        Jsonb(source) if source else None,
                        *(d.sort[c] for c in SORT_COLUMNS),
                    ]
                )
        if unique:
            await conn.execute(
                sql.SQL("UPDATE staging_documents SET dedup_hash = {}").format(dedup_expression(unique, "staging_documents"))
            )

        # Duplicates within the upload
        for key in ["doc_id", "dedup_hash"]:
            cur = await conn.execute(
                f"SELECT {key} FROM staging_documents WHERE {key} IS NOT NULL GROUP BY {key} HAVING count(*) > 1"  # type: ignore[arg-type]
            )
            if await cur.fetchall():
                what = "_id" if key == "doc_id" else "values for the unique fields"
                raise UploadError(f"The upload contains multiple documents with the same {what}")

        # Find existing documents, by id or by the values of the unique fields
        await conn.execute(
            """UPDATE staging_documents s SET target_id = d.id, target_doc_id = d.doc_id FROM documents d
               WHERE d.project_pk = %s AND d.doc_id = s.doc_id""",
            [project_pk],
        )
        if unique:
            cur = await conn.execute(
                """SELECT s.doc_id FROM staging_documents s JOIN documents d
                   ON d.project_pk = %s AND d.dedup_hash = s.dedup_hash AND d.id <> coalesce(s.target_id, -1)
                   WHERE s.doc_id IS NOT NULL""",
                [project_pk],
            )
            if conflicts := await cur.fetchall():
                raise UploadError(
                    f"Documents {_examples(conflicts)} have the same unique field values as other existing documents"
                )
            await conn.execute(
                """UPDATE staging_documents s SET target_id = d.id, target_doc_id = d.doc_id FROM documents d
                   WHERE d.project_pk = %s AND d.dedup_hash = s.dedup_hash AND s.target_id IS NULL""",
                [project_pk],
            )

        if op_type == "create":
            cur = await conn.execute("SELECT target_doc_id AS doc_id FROM staging_documents WHERE target_id IS NOT NULL")
            if existing := await cur.fetchall():
                raise UploadError(f"Documents already exist: {_examples(existing)}")
        if op_type == "update":
            cur = await conn.execute("SELECT rn, doc_id FROM staging_documents WHERE target_id IS NULL ORDER BY rn")
            if missing := await cur.fetchall():
                raise UploadError(f"Documents do not exist: {_examples(missing, 'doc_id' if missing[0]['doc_id'] else 'rn')}")  # type: ignore[index, call-overload]

        columns = f"text_data, meta_data, extra_data, source, {', '.join(SORT_COLUMNS)}"
        cur = await conn.execute(
            f"""INSERT INTO documents ({_INSERT_COLUMNS}, dedup_hash)
                SELECT %s, coalesce(doc_id, new_doc_id), {columns}, dedup_hash
                FROM staging_documents WHERE target_id IS NULL ORDER BY rn
                RETURNING id, doc_id""",  # type: ignore[arg-type]
            [project_pk],
        )
        created = await cur.fetchall()
        assignments = _MERGE if op_type in ("update", "upsert") else _REPLACE
        cur = await conn.execute(
            f"""UPDATE documents SET {assignments} FROM staging_documents s
                WHERE documents.id = s.target_id RETURNING documents.id"""  # type: ignore[arg-type]
        )
        updated = [row["id"] for row in await cur.fetchall()]  # type: ignore[index, call-overload]
        if unique and updated and op_type in ("update", "upsert"):
            # merging can change the values of unique fields
            await update_dedup_hashes(conn, project_pk, fields, updated)

        # Vectors
        if any(f.column == "vector" for f in fields.values()):
            cur = await conn.execute(
                """SELECT s.rn, d.id FROM staging_documents s JOIN documents d
                   ON d.project_pk = %s AND d.doc_id = coalesce(s.target_doc_id, s.doc_id, s.new_doc_id)""",
                [project_pk],
            )
            internal = {row["rn"]: row["id"] for row in await cur.fetchall()}  # type: ignore[index, call-overload]
            if op_type == "replace" and updated:
                await conn.execute("DELETE FROM document_vectors WHERE document_id = ANY(%s)", [updated])
            vector_rows = [(internal[rn], field_pk, v) for rn, d in enumerate(split) for field_pk, v in d.vectors.items()]
            if vector_rows:
                await store_vectors(conn, vector_rows)

    return {"created": len(created), "updated": len(updated)}


async def store_vectors(conn: AsyncConnection, rows: list[tuple[int, int, list[float]]]) -> None:
    """Store vectors (document id, field pk, vector), creating a vector index for new fields"""
    dims: dict[int, int] = {}
    for _, field_pk, vector in rows:
        if dims.setdefault(field_pk, len(vector)) != len(vector):
            raise ValueError("All vectors of a field must have the same number of dimensions")
    for field_pk, n in dims.items():
        await ensure_vector_index(conn, field_pk, n)
    async with conn.cursor() as cur:
        await cur.executemany(
            """INSERT INTO document_vectors (document_id, field_pk, embedding) VALUES (%s, %s, %s::text::public.vector)
               ON CONFLICT (field_pk, document_id) DO UPDATE SET embedding = EXCLUDED.embedding""",
            [(doc, field, json.dumps(vector)) for doc, field, vector in rows],
        )


async def ensure_vector_index(conn: AsyncConnection, field_pk: int, dims: int) -> None:
    """
    Create an HNSW index (cosine distance) for the vectors of this field. pgvector indexes need a fixed number of
    dimensions, so this is a partial expression index per field. Once it exists, inserting a vector with a
    different number of dimensions for this field fails.
    """
    await conn.execute(
        sql.SQL(
            "CREATE INDEX IF NOT EXISTS {} ON document_vectors USING hnsw ((embedding::public.vector({})) "
            "public.vector_cosine_ops) WHERE field_pk = {}"
        ).format(sql.Identifier(f"document_vectors_f{field_pk}"), sql.Literal(dims), sql.Literal(field_pk))
    )


def vector_select(f: FieldInfo) -> sql.Composable:
    """SQL expression to select the vector of a document for this field (as a json array)"""
    return sql.SQL(
        "(SELECT embedding::text::jsonb FROM document_vectors v WHERE v.document_id = documents.id AND v.field_pk = {})"
    ).format(sql.Literal(f.pk))


def field_select(f: FieldInfo) -> sql.Composable:
    """SQL expression to select the value of a field"""
    if f.column == "vector":
        return vector_select(f)
    return sql.SQL("documents.{}->{}").format(sql.Identifier(f.column), sql.Literal(f.key))


async def get_document(
    conn: AsyncConnection, project_pk: int, doc_id: str, fields: dict[str, FieldInfo], names: list[str] | None = None
) -> dict | None:
    names = list(fields.keys()) if names is None else [n for n in names if n in fields]
    columns = [sql.SQL("documents.doc_id")] + [
        sql.SQL("{} AS {}").format(field_select(fields[n]), sql.Identifier(fields[n].key)) for n in names
    ]
    cur = await conn.execute(
        sql.SQL("SELECT {} FROM documents WHERE project_pk = %s AND doc_id = %s").format(sql.SQL(", ").join(columns)),
        [project_pk, doc_id],
    )
    row = await cur.fetchone()
    if row is None:
        return None
    out: dict[str, Any] = {"_id": row["doc_id"]}  # type: ignore[index, call-overload]
    for n in names:
        value = row[fields[n].key]  # type: ignore[index, call-overload]
        if value is not None:
            out[n] = value
    return out


async def delete_document(conn: AsyncConnection, project_pk: int, doc_id: str) -> bool:
    cur = await conn.execute("DELETE FROM documents WHERE project_pk = %s AND doc_id = %s", [project_pk, doc_id])
    return cur.rowcount > 0


async def copy_batch(
    conn: AsyncConnection,
    from_project_pk: int,
    to_project_pk: int,
    field_map: dict[FieldInfo, FieldInfo],
    dest_fields: dict[str, FieldInfo],
    ids: list[int],
) -> int:
    """
    Physically copy documents (given by internal id) to another project, keeping only the fields in field_map
    (source field -> destination field). Provenance is recorded in the source column. Documents that were copied
    before (same id in the destination) are updated. Used by the copy job (amcat4.projects.jobs).
    """
    for s, d in field_map.items():
        if s.column != d.column:
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

    def sort_value(slot_column: str) -> str:
        source = [s for s, d in field_map.items() if d.sort_column == slot_column]
        if not source:
            return "NULL"
        s = source[0]
        if s.sort_column:
            return s.sort_column
        cast = {"sort_date": "timestamptz", "sort_number": "double precision", "sort_keyword": "text"}[slot_column]
        return f"({s.column}->>'{s.key}')::{cast}"

    merge = re.sub(r"\bs\.", "EXCLUDED.", _MERGE)
    stmt = f"""INSERT INTO documents ({_INSERT_COLUMNS})
               SELECT %s, doc_id, {remap("text_data")}, {remap("meta_data")}, {remap("extra_data")},
                      jsonb_build_object('project_pk', project_pk, 'doc_id', doc_id),
                      {", ".join(sort_value(c) for c in SORT_COLUMNS)}
               FROM documents WHERE project_pk = %s AND id = ANY(%s)
               ON CONFLICT (project_pk, doc_id) DO UPDATE SET {merge}
               RETURNING id"""
    async with conn.transaction():
        cur = await conn.execute(stmt, [to_project_pk, from_project_pk, ids])  # type: ignore[arg-type]
        copied = [row["id"] for row in await cur.fetchall()]  # type: ignore[index, call-overload]
        if any(f.unique for f in dest_fields.values()):
            await update_dedup_hashes(conn, to_project_pk, dest_fields, copied)
        for s, d in field_map.items():
            if s.column != "vector":
                continue
            await conn.execute(
                """INSERT INTO document_vectors (document_id, field_pk, embedding)
                   SELECT new.id, %s, v.embedding FROM document_vectors v
                   JOIN documents old ON old.id = v.document_id
                   JOIN documents new ON new.project_pk = %s AND new.doc_id = old.doc_id
                   WHERE v.field_pk = %s AND old.id = ANY(%s)
                   ON CONFLICT (field_pk, document_id) DO UPDATE SET embedding = EXCLUDED.embedding""",
                [d.pk, to_project_pk, s.pk, ids],
            )
    return len(copied)


def _project_of_field(fieldset: FieldSet, f: FieldInfo) -> int:
    for pk, fields in fieldset.project_fields.items():
        if fields.get(f.name) is f:
            return pk
    raise ValueError(f"Field {f.name} not found")


async def update_tag_by_query(
    conn: AsyncConnection,
    fieldset: FieldSet,
    query: "SearchQuery",
    field: str,
    tag: str,
    action: Literal["add", "remove"],
) -> int:
    """Add or remove a tag on all documents matching the query. Returns the number of changed documents."""
    from amcat4.postgres.search import compile_search

    c = compile_search(fieldset, query)
    updated = 0
    for f in fieldset.by_name[field]:
        if f.type != "tag":
            raise ValueError(f"Field {field} is not a tag field")
        key = sql.Literal(f.key)
        # existing values can be a single string (e.g. after changing a keyword field to a tag field)
        current = sql.SQL(
            "(CASE jsonb_typeof(meta_data->{key}) WHEN 'array' THEN meta_data->{key} "
            "WHEN 'string' THEN jsonb_build_array(meta_data->{key}) ELSE '[]'::jsonb END)"
        ).format(key=key)
        if action == "add":
            stmt = sql.SQL(
                """UPDATE documents SET meta_data = jsonb_set(meta_data, ARRAY[{key}], {current} || to_jsonb(%s::text)),
                   updated_at = now()
                   WHERE {where} AND documents.project_pk = {project} AND NOT ({current} ? %s)"""
            )
            params = [tag, *c.params, tag]
        else:
            stmt = sql.SQL(
                """UPDATE documents SET meta_data = CASE WHEN {current} - %s = '[]'::jsonb THEN meta_data - {key}
                   ELSE jsonb_set(meta_data, ARRAY[{key}], {current} - %s) END, updated_at = now()
                   WHERE {where} AND documents.project_pk = {project} AND {current} ? %s"""
            )
            params = [tag, tag, *c.params, tag]
        project = sql.Literal(_project_of_field(fieldset, f))
        cur = await conn.execute(stmt.format(key=key, current=current, where=c.where, project=project), params)
        updated += cur.rowcount
    return updated


async def update_by_query(conn: AsyncConnection, fieldset: FieldSet, query: "SearchQuery", field: str, value: Any) -> int:
    """Set (or with value=None: remove) a field on all documents matching the query. Returns the number updated."""
    from amcat4.postgres.search import compile_search

    c = compile_search(fieldset, query)
    updated = 0
    for f in fieldset.by_name[field]:
        if f.column == "vector":
            raise ValueError("Cannot update vector fields by query")
        column = sql.Identifier(f.column)
        sort = sql.SQL(", {} = %s").format(sql.Identifier(f.sort_column)) if f.sort_column else sql.SQL("")
        project = sql.Literal(_project_of_field(fieldset, f))
        if value is None:
            stmt = sql.SQL(
                "UPDATE documents SET {col} = {col} - %s::text[]{sort}, updated_at = now() "
                "WHERE {where} AND documents.project_pk = {project}"
            )
            params: list[Any] = [stored_keys(f)]
            if f.sort_column:
                params.append(None)
        else:
            stmt = sql.SQL(
                "UPDATE documents SET {col} = coalesce({col}, '{{}}') || %s{sort}, updated_at = now() "
                "WHERE {where} AND documents.project_pk = {project}"
            )
            values = stored_values(f, value)
            params = [Jsonb(values)]
            if f.sort_column:
                params.append(values[f.key])
        update = stmt.format(col=column, sort=sort, where=c.where, project=project)
        if f.unique:
            update = sql.SQL("{} RETURNING documents.id").format(update)
        async with conn.transaction():
            cur = await conn.execute(update, [*params, *c.params])
            updated += cur.rowcount
            if f.unique:
                pk = _project_of_field(fieldset, f)
                ids = [row["id"] for row in await cur.fetchall()]  # type: ignore[index, call-overload]
                await update_dedup_hashes(conn, pk, fieldset.project_fields[pk], ids)
    return updated


async def delete_by_query(conn: AsyncConnection, fieldset: FieldSet, query: "SearchQuery") -> int:
    from amcat4.postgres.search import compile_search

    c = compile_search(fieldset, query)
    cur = await conn.execute(sql.SQL("DELETE FROM documents WHERE {}").format(c.where), c.params)
    return cur.rowcount


def convert_value(value: Any, old_type: str, new_type: str) -> Any:
    """Convert a stored value to another field type (raises ValueError if that is not possible)"""
    if old_type == "tag" and new_type != "tag":
        values = value if isinstance(value, list) else [value]
        if len(values) != 1:
            raise ValueError(f"cannot convert multiple tags {values!r} to a single {new_type} value")
        value = values[0]
    if new_type in ("text", "keyword", "url", "image", "video", "audio") and isinstance(value, (dict, list)):
        value = json.dumps(value)
    if new_type in ("integer",) and isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{value} is not a whole number")
    return normalize_value(value, new_type)


async def convert_field(conn: AsyncConnection, project_pk: int, old: FieldInfo, new: FieldInfo, batch_size: int = 5000):
    """
    Convert the stored values of a field to a new type (old and new have the same pk, but a different type).
    This moves values between storage columns if needed. Raises ValueError (and changes nothing, if called within a
    transaction) if a value cannot be converted.
    """
    if (old.column == "vector") != (new.column == "vector"):
        cur = await conn.execute(
            "SELECT EXISTS (SELECT 1 FROM documents WHERE project_pk = %s AND "
            "(text_data ? %s OR meta_data ? %s OR extra_data ? %s)) AS e",
            [project_pk, old.key, old.key, old.key],
        )
        row = await cur.fetchone()
        if old.column == "vector" or row["e"]:  # type: ignore[index, call-overload]
            raise ValueError(f"Cannot convert between vector and {new.type if old.column == 'vector' else old.type} fields")
        return
    if old.column == "vector":
        return
    await conn.execute("CREATE TEMP TABLE IF NOT EXISTS converted (id bigint, vals jsonb) ON COMMIT DROP")
    last_id = 0
    old_col, new_col = sql.Identifier(old.column), sql.Identifier(new.column)
    while True:
        cur = await conn.execute(
            sql.SQL(
                "SELECT id, doc_id, {col}->{key} AS value FROM documents "
                "WHERE project_pk = %s AND id > %s AND {col} ? {key} ORDER BY id LIMIT %s"
            ).format(col=old_col, key=sql.Literal(old.key)),
            [project_pk, last_id, batch_size],
        )
        rows = await cur.fetchall()
        if not rows:
            break
        await conn.execute("TRUNCATE converted")
        async with conn.cursor().copy("COPY converted (id, vals) FROM STDIN") as copy:
            for row in rows:
                try:
                    value = convert_value(row["value"], old.type, new.type)  # type: ignore[index, call-overload]
                except (ValueError, TypeError) as e:
                    raise ValueError(f"Cannot convert document {row['doc_id']} to {new.type}: {e}")  # type: ignore[index, call-overload]
                await copy.write_row([row["id"], Jsonb(stored_values(new, value))])  # type: ignore[index, call-overload]
        removed = sql.Literal(stored_keys(old))
        if old.column == new.column:
            assignments = sql.SQL("{col} = ({col} - {removed}::text[]) || c.vals").format(col=old_col, removed=removed)
        else:
            assignments = sql.SQL("{old} = {old} - {removed}::text[], {new} = coalesce({new}, '{{}}') || c.vals").format(
                old=old_col, new=new_col, removed=removed
            )
        await conn.execute(sql.SQL("UPDATE documents SET {} FROM converted c WHERE documents.id = c.id").format(assignments))
        last_id = rows[-1]["id"]  # type: ignore[index, call-overload]
