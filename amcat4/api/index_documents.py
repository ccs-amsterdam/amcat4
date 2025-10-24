"""API Endpoints for document management."""

from typing import Annotated, Any, Literal

import elasticsearch
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from amcat4.projects import documents as _documents
from amcat4.api.auth import authenticated_user
from amcat4.models import (
    CreateDocumentField,
    FieldType,
    IndexId,
    Roles,
    User,
)
from amcat4.systemdata.roles import raise_if_not_project_index_role

app_index_documents = APIRouter(prefix="", tags=["documents"])


# REQUEST MODELS
class UploadDocumentsBody(BaseModel):
    """Form to upload documents."""

    documents: list[dict[str, Any]] = Field(description="The documents to upload")
    fields: dict[str, FieldType | CreateDocumentField] | None = Field(
        None,
        description="If a field in documents does not yet exist, you can create it on the spot. "
        "If you only need to specify the type, and use the default settings, "
        "you can use the short form: {field: type}",
    )
    operation: Literal["index", "update", "create"] = Field(
        "index",
        description="The operation to perform. Default is index, which replaces documents that already exist. "
        "The 'update' operation behaves as an upsert (create or update). If an identical document (or document with "
        "identical identifiers) already exists, the uploaded fields will be created or overwritten. If there are fields "
        "in the original document that are not in the uploaded document, they will NOT be removed. "
        "The 'create' operation only uploads new documents, and returns failures for documents with existing ids",
    )


# RESPONSE MODELS
class UploadResult(BaseModel):
    """Result of an upload operation for a single document."""

    successes: int = Field(description="Number of successful uploads")
    failures: list[dict[str, Any]] = Field(description="List of failures with details")


@app_index_documents.post("/index/{ix}/documents", status_code=status.HTTP_201_CREATED)
def upload_documents(
    ix: Annotated[IndexId, Path(description="The index id")],
    body: Annotated[UploadDocumentsBody, Body(...)],
    user: User = Depends(authenticated_user),
) -> UploadResult:
    """
    Upload documents to an index. Requires WRITER role on the index.
    """
    raise_if_not_project_index_role(user, ix, Roles.WRITER)

    result = _documents.upload_documents(ix, body.documents, body.fields, body.operation)
    return UploadResult.model_validate(result)


@app_index_documents.get("/index/{ix}/documents/{docid}")
def get_document(
    ix: Annotated[IndexId, Path(description="The index id")],
    docid: Annotated[str, Path(description="The document id")],
    fields: Annotated[str | None, Query(description="Comma-separated list of fields to retrieve")] = None,
    user: User = Depends(authenticated_user),
) -> dict[str, Any]:
    """
    Get a single document by id. Requires READER role on the index.
    """
    raise_if_not_project_index_role(user, ix, Roles.READER)
    kargs = {}
    if fields:
        kargs["_source"] = fields
    return _documents.get_document(ix, docid, **kargs)


@app_index_documents.put(
    "/index/{ix}/documents/{docid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def update_document(
    ix: Annotated[IndexId, Path(description="The index id")],
    docid: Annotated[str, Path(description="The document id")],
    update: Annotated[dict[str, Any], Body(..., description="A (partial) document. All given fields will be updated.")],
    upsert: Annotated[bool, Query(description="If true, create the document if it does not exist")] = False,
    user: User = Depends(authenticated_user),
):
    """
    Update a document. Requires WRITER role on the index.
    """
    raise_if_not_project_index_role(user, ix, Roles.WRITER)
    try:
        _documents.update_document(ix, docid, update, ignore_missing=upsert)
    except elasticsearch.exceptions.NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {ix}/{docid} not found",
        )


@app_index_documents.delete(
    "/index/{ix}/documents/{docid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(
    ix: Annotated[IndexId, Path(description="The index id")],
    docid: Annotated[str, Path(description="The document id")],
    user: User = Depends(authenticated_user),
):
    """
    Delete a document. Requires WRITER role on the index.
    """
    raise_if_not_project_index_role(user, ix, Roles.WRITER)
    _documents.delete_document(ix, docid)
