from typing import Any, Literal, Mapping

from amcat4.errors import NotFoundError
from amcat4.models import CreateDocumentField, DocumentFieldDefinition, FieldType
from amcat4.postgres import documents as storage
from amcat4.postgres.connection import connection
from amcat4.postgres.projects import project_pk
from amcat4.systemdata.fields import create_fields, field_infos


async def create_or_update_documents(
    index: str,
    documents: list[dict[str, Any]],
    fields: Mapping[str, FieldType | DocumentFieldDefinition] | None = None,
    op_type: Literal["index", "create", "update", "upsert"] = "index",
    raise_on_error=False,
    refresh=False,
):
    """
    Upload documents to this index

    :param index: The name of the index
    :param documents: A sequence of document dictionaries
    :param fields: A mapping of fieldname:type (or definition), fields will be created if they do not exist
    :param op_type: Whether to 'index' new documents (create or overwrite), 'create' (only create),
        'update' (partial update, error if not exists), or 'upsert' (partial update, create if not exists)
    :param raise_on_error: If true, raise an error if some documents could not be created/updated
    :param refresh: Not used (documents are always immediately searchable), kept for compatibility
    :return: dict(successes=<number>, failures=[...])
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
        successes, failures = await storage.upload_documents(conn, pk, documents, infos, op_type)
    if failures and raise_on_error:
        raise ValueError(f"{len(failures)} document(s) could not be saved. First error: {failures[0]}")
    return dict(successes=successes, failures=failures)


async def fetch_document(index: str, doc_id: str, _source: str | list[str] | None = None) -> dict:
    """
    Get a single document from this index.

    :param index: The name of the index
    :param doc_id: The document id
    :param _source: Optional list (or comma separated string) of fields to retrieve
    :return: the document as a {field: value} dict (without _id)
    """
    pk = await project_pk(index)
    infos = await field_infos(index)
    names = _source.split(",") if isinstance(_source, str) else _source
    async with connection() as conn:
        doc = await storage.get_document(conn, pk, doc_id, infos, names)
    if doc is None:
        raise NotFoundError(f"Document {index}/{doc_id} does not exist")
    doc.pop("_id")
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
        n, failures = await storage.upload_documents(conn, pk, [{**fields, "_id": doc_id}], infos, op_type, explicit_id=True)
    if failures:
        raise NotFoundError(f"Document {index}/{doc_id} does not exist")


async def delete_document(index: str, doc_id: str, ignore_missing: bool = False):
    """
    Delete a single document
    """
    pk = await project_pk(index)
    async with connection() as conn:
        deleted = await storage.delete_document(conn, pk, doc_id)
    if not deleted and not ignore_missing:
        raise NotFoundError(f"Document {index}/{doc_id} does not exist")
