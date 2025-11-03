"""API Endpoints for document management."""

from typing import Annotated, Any, Literal

from elasticsearch import NotFoundError
from fastapi import APIRouter, Body, Depends, HTTPException, Header, Path, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from amcat4.api.auth import authenticated_user
from amcat4.models import (
    CreateDocumentField,
    FieldType,
    IndexId,
    Roles,
    User,
)
from amcat4.objectstorage import s3bucket
from amcat4.projects.documents import delete_document, fetch_document, update_document, create_or_update_documents
from amcat4.systemdata.fields import HTTPException_if_invalid_multimedia_field
from amcat4.systemdata.roles import HTTPException_if_not_project_index_role

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
    HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)

    result = create_or_update_documents(ix, body.documents, body.fields, body.operation)
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
    HTTPException_if_not_project_index_role(user, ix, Roles.READER)
    kargs = {}
    if fields:
        kargs["_source"] = fields
    try:
        return fetch_document(ix, docid, **kargs)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {ix}/{docid} not found",
        )


@app_index_documents.put(
    "/index/{ix}/documents/{docid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def modify_document(
    ix: Annotated[IndexId, Path(description="The index id")],
    docid: Annotated[str, Path(description="The document id")],
    update: Annotated[dict[str, Any], Body(..., description="A (partial) document. All given fields will be updated.")],
    upsert: Annotated[bool, Query(description="If true, create the document if it does not exist")] = False,
    user: User = Depends(authenticated_user),
):
    """
    Update a document. Requires WRITER role on the index.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
    try:
        update_document(ix, docid, update, ignore_missing=upsert)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {ix}/{docid} not found",
        )


@app_index_documents.delete(
    "/index/{ix}/documents/{docid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_document(
    ix: Annotated[IndexId, Path(description="The index id")],
    docid: Annotated[str, Path(description="The document id")],
    user: User = Depends(authenticated_user),
):
    """
    Delete a document. Requires WRITER role on the index.
    """
    HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
    try:
        delete_document(ix, docid)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {ix}/{docid} not found",
        )


@app_index_documents.get("/index/{ix}/documents/{doc_id}/multimedia/{field}")
def multimedia_get_gatekeeper(
    ix: str,
    doc_id: str,
    field: str,
    etag: str | None = Query(None, description="ETag can be included in query for immutable caching"),
    if_none_match: str | None = Header(None, alias="If-None-Match"),
    user: User = Depends(authenticated_user),
):
    """
    Gatekeeper endpoint for multimedia GET requests.
    """
    # This validates both role access and whether field is a valid multimedia field
    # (meaning that the field value can be used as an objectstorage key)
    HTTPException_if_invalid_multimedia_field(ix, field, user)

    bucket = s3bucket.bucket_name(ix)
    url = fetch_document(ix, doc_id, source_includes=[field]).get(field)

    if not url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"field '{field}' not found in document.")

    # Cached flow: if the client provides a valid If-None-Match header, return immediately (dont auth for efficiency)
    # (the browser gets the ETag from the S3 redirect response)
    if if_none_match:
        current_etag = s3bucket.get_etag(bucket, url)
        if if_none_match.strip('"') == current_etag:
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": f'"{current_etag}"'})

    # Fetch flow: presigned url to s3
    # If etag is provided in the query, we assume the client wants immutable caching
    cache_control_value = "public, max-age=3153600, immutable" if etag else "no-cache, must-revalidate"
    presigned_url = s3bucket.presigned_get(bucket, url, ResponseCacheControl=cache_control_value)

    return RedirectResponse(url=presigned_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
