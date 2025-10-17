"""API Endpoints for document and index management."""

from typing import Annotated, Any, Literal

import elasticsearch
from fastapi import APIRouter, Body, Depends, HTTPException, Response, status

from amcat4.api.index import app_index
from amcat4.projects.documents import (
    upload_documents as _upload_documents,
    get_document as _get_document,
    update_document as _update_document,
    delete_document as _delete_document,
)
from amcat4.api.auth import authenticated_user
from amcat4.models import (
    CreateField,
    FieldType,
    Role,
    User,
)
from amcat4.systemdata.roles import raise_if_not_project_index_role


@app_index.post("/{ix}/documents", status_code=status.HTTP_201_CREATED)
def upload_documents(
    ix: str,
    documents: Annotated[list[dict[str, Any]], Body(description="The documents to upload")],
    fields: Annotated[
        dict[str, FieldType | CreateField] | None,
        Body(
            description="If a field in documents does not yet exist, you can create it on the spot. "
            "If you only need to specify the type, and use the default settings, "
            "you can use the short form: {field: type}"
        ),
    ] = None,
    operation: Annotated[
        Literal["index", "update", "create"],
        Body(
            description="The operation to perform. Default is index, which replaces documents that already exist. "
            "The 'update' operation behaves as an upsert (create or update). If an identical document (or document with "
            "identical identifiers) already exists, the uploaded fields will be created or overwritten. If there are fields "
            "in the original document that are not in the uploaded document, they will NOT be removed. "
            "The 'create' operation only uploads new documents, and returns failures for documents with existing ids"
        ),
    ] = "index",
    user: User = Depends(authenticated_user),
):
    """
    Upload documents to this server. Returns a list of ids for the uploaded documents
    """
    raise_if_not_project_index_role(user, ix, Role.WRITER)
    return _upload_documents(ix, documents, fields, operation)


@app_index.get("/{ix}/documents/{docid}")
def get_document(
    ix: str,
    docid: str,
    fields: str | None = None,
    user: User = Depends(authenticated_user),
):
    """
    Get a single document by id.

    GET request parameters:
    fields - Comma separated list of fields to return (default: all fields)
    """
    raise_if_not_project_index_role(user, ix, Role.READER)
    kargs = {}
    if fields:
        kargs["_source"] = fields
    try:
        return _get_document(ix, docid, **kargs)
    except elasticsearch.exceptions.NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {ix}/{docid} not found",
        )


@app_index.put(
    "/{ix}/documents/{docid}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def update_document(
    ix: str,
    docid: str,
    update: dict = Body(...),
    user: User = Depends(authenticated_user),
):
    """
    Update a document.

    PUT request body should be a json {field: value} mapping of fields to update
    """
    raise_if_not_project_index_role(user, ix, Role.WRITER)
    try:
        _update_document(ix, docid, update)
    except elasticsearch.exceptions.NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {ix}/{docid} not found",
        )


@app_index.delete(
    "/{ix}/documents/{docid}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_document(ix: str, docid: str, user: User = Depends(authenticated_user)):
    """Delete this document."""
    raise_if_not_project_index_role(user, ix, Role.WRITER)
    try:
        _delete_document(ix, docid)
    except elasticsearch.exceptions.NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {ix}/{docid} not found",
        )
