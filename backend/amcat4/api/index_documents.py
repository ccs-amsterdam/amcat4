"""API Endpoints for document management."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from amcat4.api.auth_helpers import authenticated_user
from amcat4.errors import NotFoundError
from amcat4.models import (
    DocumentFieldDefinition,
    FieldType,
    IndexId,
    Roles,
    User,
)
from amcat4.postgres.documents import OpType, UploadError
from amcat4.projects.documents import create_or_update_documents, delete_document, fetch_document, update_document
from amcat4.systemdata.fields import field_access
from amcat4.systemdata.roles import HTTPException_if_not_project_index_role

app_index_documents = APIRouter(prefix="", tags=["documents"])


# REQUEST MODELS
class UploadDocumentsBody(BaseModel):
    """Form to upload documents."""

    documents: list[dict[str, Any]] = Field(description="The documents to upload")
    fields: dict[str, FieldType | DocumentFieldDefinition] | None = Field(
        None,
        description="Field type definitions need to be explicitly defined before uploading documents. "
        "By providing them here, they will be created when uploading the documents, and verified if they already exist. ",
    )
    operation: OpType = Field(
        "replace",
        description="What to do with documents that already exist (documents are matched by _id, or by the values "
        "of the unique fields). "
        "'create' only adds new documents, and fails if any document already exists. "
        "'update' only updates existing documents (uploaded fields are overwritten, other fields are kept), "
        "and fails if any document does not exist. "
        "'upsert' creates new documents and updates existing documents. "
        "'replace' (default) creates new documents and replaces existing documents completely. "
        "Uploads are all-or-nothing: if any document fails, nothing is saved.",
    )


# RESPONSE MODELS
class UploadResult(BaseModel):
    """Result of an upload"""

    created: int = Field(description="Number of new documents")
    updated: int = Field(description="Number of existing documents that were updated or replaced")


@app_index_documents.post("/index/{ix}/documents", status_code=status.HTTP_201_CREATED)
async def upload_documents(
    ix: Annotated[IndexId, Path(description="The index id")],
    body: Annotated[UploadDocumentsBody, Body(...)],
    user: User = Depends(authenticated_user),
) -> UploadResult:
    """
    Upload documents to an index. Requires WRITER role on the index.
    If the upload fails (e.g. invalid values, or existing documents for 'create'), nothing is saved and the
    error is returned (409 for conflicts with existing documents, 422 for invalid documents).
    """
    await HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)

    try:
        result = await create_or_update_documents(ix, body.documents, body.fields, body.operation)
    except UploadError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    return UploadResult.model_validate(result)


@app_index_documents.get("/index/{ix}/documents/{docid}")
async def get_document(
    ix: Annotated[IndexId, Path(description="The index id")],
    docid: Annotated[str, Path(description="The document id")],
    fields: Annotated[str | None, Query(description="Comma-separated list of fields to retrieve")] = None,
    user: User = Depends(authenticated_user),
) -> dict[str, Any]:
    """
    Get a single document by id. Requires READER role on the index, and only returns the fields that are visible
    to the user.
    """
    await HTTPException_if_not_project_index_role(user, ix, Roles.READER)
    visible = [name for name, spec in (await field_access(user, [ix])).visible.items() if spec.snippet is None]
    names = [f for f in fields.split(",") if f in visible] if fields else visible
    try:
        return await fetch_document(ix, docid, names)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {ix}/{docid} not found",
        )


@app_index_documents.put(
    "/index/{ix}/documents/{docid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def modify_document(
    ix: Annotated[IndexId, Path(description="The index id")],
    docid: Annotated[str, Path(description="The document id")],
    update: Annotated[dict[str, Any], Body(..., description="A (partial) document. All given fields will be updated.")],
    upsert: Annotated[bool, Query(description="If true, create the document if it does not exist")] = False,
    user: User = Depends(authenticated_user),
):
    """
    Update a document. Requires WRITER role on the index.
    """
    await HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
    try:
        await update_document(ix, docid, update, ignore_missing=upsert)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {ix}/{docid} not found",
        )


@app_index_documents.delete(
    "/index/{ix}/documents/{docid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_document(
    ix: Annotated[IndexId, Path(description="The index id")],
    docid: Annotated[str, Path(description="The document id")],
    user: User = Depends(authenticated_user),
):
    """
    Delete a document. Requires WRITER role on the index.
    """
    await HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
    try:
        await delete_document(ix, docid)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {ix}/{docid} not found",
        )
