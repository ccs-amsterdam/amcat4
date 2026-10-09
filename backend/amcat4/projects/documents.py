from typing import Any, Literal, Mapping

from psycopg import sql

from amcat4.errors import NotFoundError
from amcat4.models import CreateDocumentField, DocumentFieldDefinition, FieldType
from amcat4.postgres import documents as storage
from amcat4.postgres.connection import connection
from amcat4.postgres.documents import OpType
from amcat4.postgres.layout import project_filter
from amcat4.postgres.projects import project_pk
from amcat4.systemdata.fields import create_fields, field_infos


async def create_or_update_documents(
    index: str,
    documents: list[dict[str, Any]],
    fields: Mapping[str, FieldType | DocumentFieldDefinition] | None = None,
    op_type: OpType = "replace",
) -> dict[str, int]:
    """
    Upload documents to this index. This is a single transaction: if any document cannot be saved, nothing is saved
    and an UploadError (a ValueError) is raised.

    :param index: The name of the index
    :param documents: A sequence of document dictionaries
    :param fields: A mapping of fieldname:type (or definition), fields will be created if they do not exist
    :param op_type: create (only new documents), update (existing documents, keeping fields that are not given),
                    upsert (update or create), replace (replace the whole document, or create)
    :return: dict(created=<number>, updated=<number>)
    """
    if fields:
        create_fields_dict: dict[str, CreateDocumentField] = dict()
        for k, v in fields.items():
            if isinstance(v, str):
                create_fields_dict[k] = CreateDocumentField(type=v)
            else:
                create_fields_dict[k] = CreateDocumentField(**v.model_dump())
        await create_fields(index, create_fields_dict)

    pk = await project_pk(index)
    infos = await field_infos(index)
    async with connection() as conn:
        return await storage.upload_documents(conn, pk, documents, infos, op_type)


async def fetch_document(index: str, doc_id: str, _source: str | list[str] | None = None) -> dict:
    """
    Get a single document from this index.

    :param index: The name of the index
    :param doc_id: The document id
    :param _source: Optional list (or comma separated string) of fields to retrieve
    :return: the document as a {field: value} dict (without _id). If the document was copied from another project,
             _copied_from contains the source project and document id.
    """
    pk = await project_pk(index)
    infos = await field_infos(index)
    names = _source.split(",") if isinstance(_source, str) else _source
    async with connection() as conn:
        doc = await storage.get_document(conn, pk, doc_id, infos, names)
        if doc is None:
            raise NotFoundError(f"Document {index}/{doc_id} does not exist")
        doc.pop("_id")
        cur = await conn.execute(
            sql.SQL(
                """SELECT p.id AS project, d.copied_from->>'doc_id' AS doc_id FROM documents d
                   JOIN projects p ON p.pk = (d.copied_from->>'project_pk')::int WHERE {} AND d.doc_id = %s"""
            ).format(await project_filter(conn, pk, "d")),
            [doc_id],
        )
        row = await cur.fetchone()
    if row:
        doc["_copied_from"] = row
    return doc


async def update_document(index: str, doc_id: str, fields: dict, ignore_missing: bool = False, get_source=False):
    """
    Update a single document.

    :param index: The name of the index
    :param doc_id: The document id
    :param fields: a {field: value} mapping of fields to update
    :param ignore_missing: If True, create the document if it does not exist
    """
    pk = await project_pk(index)
    infos = await field_infos(index)
    op_type: Literal["update", "upsert"] = "upsert" if ignore_missing else "update"
    async with connection() as conn:
        try:
            await storage.upload_documents(conn, pk, [{**fields, "_id": doc_id}], infos, op_type)
        except storage.UploadError as e:
            if op_type == "update" and "do not exist" in str(e):
                raise NotFoundError(f"Document {index}/{doc_id} does not exist")
            raise


async def delete_document(index: str, doc_id: str, ignore_missing: bool = False):
    """
    Delete a single document
    """
    pk = await project_pk(index)
    async with connection() as conn:
        deleted = await storage.delete_document(conn, pk, doc_id)
    if not deleted and not ignore_missing:
        raise NotFoundError(f"Document {index}/{doc_id} does not exist")
