import hashlib
import json
import logging
from typing import Any, Literal, Mapping

import elasticsearch.helpers

from amcat4.elastic import es
from amcat4.models import CreateDocumentField, DocumentFieldDefinition, FieldType
from amcat4.systemdata.fields import coerce_type, create_fields, create_or_verify_tag_field, list_fields


def create_or_update_documents(
    index: str,
    documents: list[dict[str, Any]],
    fields: Mapping[str, FieldType | DocumentFieldDefinition] | None = None,
    op_type: Literal["index", "create", "update"] = "index",
    raise_on_error=False,
):
    """
    Upload documents to this index

    :param index: The name of the index (without prefix)
    :param documents: A sequence of article dictionaries
    :param fields: A mapping of fieldname:UpdateField for field types
    :param op_type: Whether to 'index' new documents (create or overwrite), 'create' (only create) or 'update' existing documents
    """
    if fields:
        create_fields_dict: dict[str, CreateDocumentField] = dict()
        for k, v in fields.items():
            if isinstance(v, str):
                create_fields_dict[k] = CreateDocumentField(type=v)
            else:
                create_fields_dict[k] = CreateDocumentField(**v.model_dump())

        create_fields(index, create_fields_dict)

    actions = list(upload_document_es_actions(index, documents, op_type))
    try:
        successes, failures = elasticsearch.helpers.bulk(
            es(),
            actions,
            stats_only=False,
            raise_on_error=raise_on_error,
        )
    except elasticsearch.helpers.BulkIndexError as e:
        logging.error("Error on indexing: " + json.dumps(e.errors, indent=2, default=str))
        if e.errors:
            _, error = list(e.errors[0].items())[0]
            reason = error.get("error", {}).get("reason", error)
            e.args = e.args + (f"First error: {reason}",)
        raise

    return dict(successes=successes, failures=failures)


def upload_document_es_actions(index, documents, op_type):
    field_settings = list_fields(index)
    identifiers = [k for k, v in field_settings.items() if v.identifier is True]
    for document in documents:
        doc = dict()
        action = {"_op_type": op_type, "_index": index}

        for key in document.keys():
            if key in field_settings:
                doc[key] = coerce_type(document[key], field_settings[key].type)
            elif key == "_id":
                if len(identifiers) > 0:
                    raise ValueError(f"This index uses identifiers ({identifiers}), so you cannot set the _id directly.")
                action["_id"] = document[key]
            else:
                raise ValueError(f"Field '{key}' is not yet specified")

        if len(identifiers) > 0:
            action["_id"] = _create_document_id(document, identifiers)
            # if no _id is given and no identifiers are used, elasticsearch creates a cool unique one

        # https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html
        if op_type == "update":
            if "_id" not in action:
                raise ValueError("Update requires _id")
            action["doc"] = doc
            action["doc_as_upsert"] = True
        else:
            action = {**doc, **action}

        yield action


def fetch_document(index: str, doc_id: str, **kargs) -> dict:
    """
    Get a single document from this index.

    :param index: The name of the index
    :param doc_id: The document id (hash)
    :return: the source dict of the document
    """
    return es().get(index=index, id=doc_id, **kargs)["_source"]


def update_document(
    index: str, doc_id: str, fields: dict, ignore_missing: bool = False, get_source: bool | Mapping[str, Any] = False
):
    """
    Update a single document.

    :param index: The name of the index
    :param doc_id: The document id (hash)
    :param fields: a {field: value} mapping of fields to update
    :param ignore_missing: If True, create the document if it does not exist
    :param get_source: If True, return the updated document source
    """
    es().update(index=index, id=doc_id, doc=fields, source=get_source, doc_as_upsert=ignore_missing)  # type: ignore


def delete_document(index: str, doc_id: str, ignore_missing: bool = False):
    """
    Delete a single document

    :param index: The Pname of the index
    :param doc_id: The document id (hash)
    """
    es().delete(index=index, id=doc_id)


UPDATE_SCRIPTS = dict(
    add="""
    if (ctx._source[params.field] == null) {
      ctx._source[params.field] = [params.tag]
    } else {
      if (ctx._source[params.field].contains(params.tag)) {
        ctx.op = 'noop';
      } else {
        ctx._source[params.field].add(params.tag)
      }
    }
    """,
    remove="""
    if (ctx._source[params.field] != null && ctx._source[params.field].contains(params.tag)) {
      ctx._source[params.field].removeAll([params.tag]);
      if (ctx._source[params.field].size() == 0) {
        ctx._source.remove(params.field);
      }
    } else {
      ctx.op = 'noop';
    }
    """,
)


def update_document_tag_by_query(
    index: str | list[str],
    action: Literal["add", "remove"],
    query: dict,
    field: str,
    tag: str,
):
    create_or_verify_tag_field(index, field)
    script = dict(
        source=UPDATE_SCRIPTS[action],
        lang="painless",
        params=dict(field=field, tag=tag),
    )
    result = es().update_by_query(index=index, script=script, **query, refresh=True)
    return dict(updated=result["updated"], total=result["total"])


def update_documents_by_query(index: str | list[str], query: dict, field: str, value: Any):
    if value is None:
        script = dict(
            source="ctx._source.remove(params.field)",
            lang="painless",
            params=dict(field=field),
        )
    else:
        script = dict(
            source="ctx._source[params.field] = params.value",
            lang="painless",
            params=dict(field=field, value=value),
        )

    result = es().update_by_query(index=index, query=query, script=script, refresh=True)
    return dict(updated=result["updated"], total=result["total"])


def delete_documents_by_query(index: str | list[str], query: dict):
    result = es().delete_by_query(index=index, query=query)
    return dict(updated=result["deleted"], total=result["total"])


def _create_document_id(document: dict, identifiers: list[str]) -> str:
    """
    Create the _id for a document.
    """

    if len(identifiers) == 0:
        raise ValueError("Can only create id if identifiers are specified")

    id_keys = sorted(set(identifiers) & set(document.keys()))
    id_fields = {k: document[k] for k in id_keys}
    hash_str = json.dumps(id_fields, sort_keys=True, ensure_ascii=True, default=str).encode("ascii")
    m = hashlib.sha224()
    m.update(hash_str)
    return m.hexdigest()
