"""
Document storage.

Documents are uploaded via COPY into a temporary staging table, followed by a single INSERT/UPDATE statement.
This is fast and gives us proper create / replace / update / upsert semantics.
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

# index: create or replace; create: only create new documents; update: update existing documents (merge fields);
# upsert: update or create
OpType = Literal["index", "create", "update", "upsert"]

SORT_COLUMNS = ["sort_date", "sort_number", "sort_keyword"]


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


def document_id(document: dict[str, Any], fields: dict[str, FieldInfo], op_type: OpType, explicit_id: bool = False) -> str:
    """
    Determine the id of a document. If the project has identifier fields, the id is a hash of the identifier
    values, so uploading the same document twice does not create a duplicate. Otherwise it is the given _id,
    or a random id.
    """
    identifiers = sorted((f for f in fields.values() if f.identifier), key=lambda f: f.name)
    if identifiers:
        if "_id" in document and document["_id"] is not None:
            if op_type == "update" or explicit_id:
                return str(document["_id"])
            raise ValueError(f"This index uses identifiers ({[f.name for f in identifiers]}), so you cannot set the _id")
        return identifier_hash(document, identifiers)
    if document.get("_id") is not None:
        return str(document["_id"])
    if op_type == "update":
        raise ValueError("Update requires _id")
    return uuid.uuid4().hex


def identifier_hash(document: dict[str, Any], identifiers: list[FieldInfo]) -> str:
    values = {f.name: document[f.name] for f in identifiers if f.name in document}
    hash_str = json.dumps(values, sort_keys=True, ensure_ascii=True, default=str).encode("ascii")
    return hashlib.sha224(hash_str).hexdigest()


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
    rn integer, doc_id text, text_data jsonb, meta_data jsonb, extra_data jsonb, source jsonb,
    sort_date timestamptz, sort_number double precision, sort_keyword text
) ON COMMIT DELETE ROWS
"""

_INSERT_COLUMNS = "project_pk, doc_id, text_data, meta_data, extra_data, source, sort_date, sort_number, sort_keyword"

_MERGE = """text_data = documents.text_data || EXCLUDED.text_data,
            meta_data = documents.meta_data || EXCLUDED.meta_data,
            extra_data = coalesce(documents.extra_data, '{}') || coalesce(EXCLUDED.extra_data, '{}'),
            sort_date = coalesce(EXCLUDED.sort_date, documents.sort_date),
            sort_number = coalesce(EXCLUDED.sort_number, documents.sort_number),
            sort_keyword = coalesce(EXCLUDED.sort_keyword, documents.sort_keyword),
            updated_at = now()"""

_REPLACE = """text_data = EXCLUDED.text_data, meta_data = EXCLUDED.meta_data, extra_data = EXCLUDED.extra_data,
              sort_date = EXCLUDED.sort_date, sort_number = EXCLUDED.sort_number, sort_keyword = EXCLUDED.sort_keyword,
              updated_at = now()"""


async def upload_documents(
    conn: AsyncConnection,
    project_pk: int,
    documents: list[dict[str, Any]],
    fields: dict[str, FieldInfo],
    op_type: OpType = "index",
    source: dict | None = None,
    explicit_id: bool = False,
) -> tuple[int, list[dict]]:
    """
    Upload documents to a project. Returns the number of created/updated documents, and a list of failures
    (documents that already exist for op_type=create, or that do not exist for op_type=update).
    """
    split = {}
    for doc in documents:
        doc_id = document_id(doc, fields, op_type, explicit_id)
        split[doc_id] = SplitDocument(doc, fields)  # later duplicates in a batch override earlier ones

    async with conn.transaction():
        await conn.execute(_STAGING)
        async with conn.cursor().copy(
            "COPY staging_documents (rn, doc_id, text_data, meta_data, extra_data, source, sort_date, sort_number, "
            "sort_keyword) FROM STDIN"
        ) as copy:
            for rn, (doc_id, d) in enumerate(split.items()):
                extra = d.columns["extra_data"]
                await copy.write_row(
                    [
                        rn,
                        doc_id,
                        Jsonb(d.columns["text_data"]),
                        Jsonb(d.columns["meta_data"]),
                        Jsonb(extra) if extra else None,
                        Jsonb(source) if source else None,
                        *(d.sort[c] for c in SORT_COLUMNS),
                    ]
                )
        columns = f"doc_id, text_data, meta_data, extra_data, source, {', '.join(SORT_COLUMNS)}"
        insert = f"INSERT INTO documents ({_INSERT_COLUMNS}) SELECT %s, {columns} FROM staging_documents"
        if op_type == "update":
            stmt = f"""UPDATE documents SET {_MERGE.replace("EXCLUDED.", "s.")}
                       FROM staging_documents s WHERE documents.project_pk = %s AND documents.doc_id = s.doc_id
                       RETURNING documents.id, documents.doc_id"""
        elif op_type == "create":
            stmt = f"{insert} ON CONFLICT (project_pk, doc_id) DO NOTHING RETURNING id, doc_id"
        elif op_type == "upsert":
            stmt = f"{insert} ON CONFLICT (project_pk, doc_id) DO UPDATE SET {_MERGE} RETURNING id, doc_id"
        else:
            stmt = f"{insert} ON CONFLICT (project_pk, doc_id) DO UPDATE SET {_REPLACE} RETURNING id, doc_id"
        cur = await conn.execute(stmt, [project_pk])  # type: ignore[arg-type]
        done = {row["doc_id"]: row["id"] for row in await cur.fetchall()}  # type: ignore[index, call-overload]

        vector_rows = [
            (done[doc_id], field_pk, vector)
            for doc_id, d in split.items()
            if doc_id in done
            for field_pk, vector in d.vectors.items()
        ]
        if op_type == "index" and any(f.column == "vector" for f in fields.values()):
            await conn.execute("DELETE FROM document_vectors WHERE document_id = ANY(%s)", [list(done.values())])
        if vector_rows:
            await store_vectors(conn, vector_rows)

    failures = []
    for doc_id in split:
        if doc_id not in done:
            reason = "document already exists" if op_type == "create" else "document does not exist"
            failures.append({"_id": doc_id, "error": reason})
    return len(done), failures


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


async def copy_documents(
    conn: AsyncConnection,
    from_project_pk: int,
    to_project_pk: int,
    field_map: dict[FieldInfo, FieldInfo],
    where_sql: sql.Composable | str = "TRUE",
    where_params: list | None = None,
) -> int:
    """
    Physically copy documents (or a subset selected by where_sql) to another project, keeping only the
    fields in field_map (source field -> destination field). Provenance is recorded in the source column.
    Existing documents (with the same id) in the destination are updated.
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

    where = sql.SQL(where_sql) if isinstance(where_sql, str) else where_sql  # type: ignore[arg-type]
    # (composed rather than formatted, because the statement contains literal braces)
    stmt = sql.Composed(
        [
            sql.SQL(
                f"""INSERT INTO documents ({_INSERT_COLUMNS})
                SELECT %s, doc_id, {remap("text_data")}, {remap("meta_data")}, {remap("extra_data")},
                       jsonb_build_object('project_pk', project_pk, 'doc_id', doc_id),
                       {", ".join(sort_value(c) for c in SORT_COLUMNS)}
                FROM documents WHERE project_pk = %s AND ("""  # type: ignore[arg-type]
            ),
            where,
            sql.SQL(f") ON CONFLICT (project_pk, doc_id) DO UPDATE SET {_MERGE} RETURNING id"),  # type: ignore[arg-type]
        ]
    )
    async with conn.transaction():
        cur = await conn.execute(stmt, [to_project_pk, from_project_pk, *(where_params or [])])
        copied = await cur.fetchall()
        for s, d in field_map.items():
            if s.column != "vector":
                continue
            await conn.execute(
                """INSERT INTO document_vectors (document_id, field_pk, embedding)
                   SELECT new.id, %s, v.embedding FROM document_vectors v
                   JOIN documents old ON old.id = v.document_id AND old.project_pk = %s
                   JOIN documents new ON new.project_pk = %s AND new.doc_id = old.doc_id
                   WHERE v.field_pk = %s
                   ON CONFLICT (field_pk, document_id) DO UPDATE SET embedding = EXCLUDED.embedding""",
                [d.pk, from_project_pk, to_project_pk, s.pk],
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
        cur = await conn.execute(stmt.format(col=column, sort=sort, where=c.where, project=project), [*params, *c.params])
        updated += cur.rowcount
    return updated


async def delete_by_query(conn: AsyncConnection, fieldset: FieldSet, query: "SearchQuery") -> int:
    from amcat4.postgres.search import compile_search

    c = compile_search(fieldset, query)
    cur = await conn.execute(sql.SQL("DELETE FROM documents WHERE {}").format(c.where), c.params)
    return cur.rowcount
