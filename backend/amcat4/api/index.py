"""API Endpoints for document and index management."""

import base64
import gzip
import io
import json
import zlib
from typing import Annotated

from elastic_transport import ApiError
from elasticsearch import ConflictError, NotFoundError
from fastapi import APIRouter, Body, Depends, File, HTTPException, Path, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from amcat4.api.auth_helpers import authenticated_user
from amcat4.api.index_query import FiltersType, QueriesType, _standardize_filters, _standardize_queries
from amcat4.config import get_settings
from amcat4.models import (
    ContactInfo,
    CreateDocumentField,
    FieldSpec,
    FieldType,
    GuestRole,
    IndexId,
    ProjectSettings,
    Role,
    RoleEmailPattern,
    Roles,
    User,
)
from amcat4.objectstorage.image_processing import create_image_from_bytes, create_image_from_url
from amcat4.projects.documents import create_or_update_documents
from amcat4.projects.index import (
    IndexAlreadyExists,
    IndexDoesNotExist,
    archive_project_index,
    create_project_index,
    delete_project_index,
    index_size_in_bytes,
    list_unregistered_indices,
    list_user_project_indices,
    refresh_index,
    register_project_index,
    update_project_index,
)
from amcat4.projects.query import query_documents, reindex
from amcat4.systemdata.fields import create_fields, list_fields
from amcat4.systemdata.roles import (
    HTTPException_if_not_project_index_role,
    HTTPException_if_not_server_role,
    create_project_role,
    get_project_guest_role,
    get_user_project_role,
    list_project_roles,
    set_project_guest_role,
    update_project_role,
)
from amcat4.systemdata.settings import get_project_image, get_project_settings

app_index = APIRouter(prefix="", tags=["index"])

# TODO: rename to projects and add deprecated index route
# app_projects = APIRouter(prefix="/projects", tags=["projects"])
# app_index_deprecated = APIRouter(prefix="/projects", tags=["projects"], deprecated=True)
#
# add both decorators to all functions, and register both routers


# REQUEST MODELS
class UpdateIndexBody(BaseModel):
    """Form to update an existing index."""

    name: str | None = Field(default=None, description="Name of the index")
    description: str | None = Field(default=None, description="Description of the index")
    guest_role: GuestRole | None = Field(default=None, description="Guest role for the index")
    folder: str | None = Field(default=None, description="Folder for the index")
    contact: list[ContactInfo] | None = Field(default=None, description="Contact info for the index")


class CreateIndexBody(UpdateIndexBody):
    """Form to create a new index."""

    id: IndexId = Field(description="ID of the new index")


class FieldReindexOptions(BaseModel):
    """Per-field options for reindexing."""

    rename: str | None = None
    exclude: bool = False
    type: FieldType | None = None


class ReindexBody(BaseModel):
    """Body for reindexing documents."""

    destination: str = Field(description="The destination index id")
    queries: QueriesType
    filters: FiltersType
    field_options: dict[str, FieldReindexOptions] = {}


# RESPONSE MODELS


class IndexListResponse(BaseModel):
    id: IndexId = Field(description="ID of the index")
    name: str | None = Field(description="Name of the index")
    user_role: Role | None = Field(description="Role of the current user on this index")
    archived: str | None = Field(description="Timestamp of when the index was archived, or null if not archived")
    description: str | None = Field(description="Description of the index")
    user_role_match: RoleEmailPattern | None = Field(description="Email pattern that determined the user role")
    folder: str | None = Field(description="Folder for the index")
    image_url: str | None = Field(description="URL of the index thumbnail image")


class IndexViewResponse(IndexListResponse):
    guest_role: GuestRole | None = Field(description="Guest role for the index")
    contact: list[ContactInfo] | None = Field(description="Contact info for the index")
    bytes: int = Field(description="Size of the index in bytes")


@app_index.get("/index")
async def index_list(
    request: Request,
    show_all: Annotated[
        bool, Query(..., description="Also show indices user has no role on (requires ADMIN server role)")
    ] = False,
    show_archived: Annotated[bool, Query(..., description="If true, include archived indices in the list")] = False,
    minimal: Annotated[
        bool, Query(..., description="If true, return a dictionary with index ids as keys and roles as values")
    ] = False,
    user: User = Depends(authenticated_user),
) -> list[IndexListResponse] | dict[IndexId, Role | None]:
    """
    List indices from this server that the user has access to. Returns a list of dicts with index details,
    including the user role.
    Requires at least OBSERVER role on the index. If show_all is true, requires ADMIN server role and shows all indices.
    """
    if show_all:
        await HTTPException_if_not_server_role(user, Roles.ADMIN)

    ix_list: list = []
    ix_dict: dict[IndexId, Role | None] = {}
    async for ix, role in list_user_project_indices(user, show_all=show_all, show_archived=show_archived):
        image_url = f"{get_settings().host}/api/index/{ix.id}/image/{ix.image.id}" if ix.image else None

        if minimal:
            ix_dict[ix.id] = role.role if role else None
        else:
            ix_list.append(
                IndexListResponse(
                    id=ix.id,
                    name=ix.name or "",
                    user_role=role.role if role else None,
                    archived=str(ix.archived or ""),
                    description=ix.description or "",
                    folder=ix.folder or "",
                    image_url=image_url,
                    user_role_match=role.email if role else None,
                )
            )

    if minimal:
        return ix_dict
    else:
        return ix_list


@app_index.post("/index", status_code=status.HTTP_201_CREATED)
async def create_index(
    body: Annotated[CreateIndexBody, Body(...)],
    user: User = Depends(authenticated_user),
):
    """
    Create a new index with the current user (you) as admin. Requires WRITER role on the server.
    """
    await HTTPException_if_not_server_role(
        user, Roles.WRITER, message="Creating a new project requires WRITER permission on the server"
    )

    d = body.model_dump()

    try:
        await create_project_index(
            ProjectSettings(**d),
            user.email,
        )
    except IndexAlreadyExists as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ApiError as e:
        raise HTTPException(
            status_code=400,
            detail=dict(info=f"Error on creating index: {e}", message=e.message, body=e.body),
        )

    if body.guest_role:
        await set_project_guest_role(body.id, Roles[body.guest_role])


@app_index.post("/index/{ix}/register", status_code=status.HTTP_201_CREATED)
async def register_index(
    ix: Annotated[IndexId, Path(..., description="ID of the existing elasticsearch index to register")],
    body: Annotated[UpdateIndexBody, Body(...)],
    user: User = Depends(authenticated_user),
):
    """
    Register an existing elasticsearch index as an amcat project.
    The elasticsearch index must already exist and not yet be registered. Requires ADMIN server role.
    """
    await HTTPException_if_not_server_role(
        user, Roles.ADMIN, message="Registering an existing index requires ADMIN permission on the server"
    )

    d = body.model_dump(exclude={"image_url"})
    d["image"] = await create_image_from_url(body.image_url) if body.image_url else None
    d["id"] = ix

    try:
        await register_project_index(ProjectSettings(**d), user.email)
    except IndexDoesNotExist as e:
        raise HTTPException(status_code=404, detail=str(e))
    except IndexAlreadyExists as e:
        raise HTTPException(status_code=409, detail=str(e))

    if body.guest_role:
        await set_project_guest_role(ix, Roles[body.guest_role])


@app_index.get("/index/unregistered")
async def list_unregistered(user: User = Depends(authenticated_user)) -> list[str]:
    """
    List all elasticsearch indices that exist but are not registered as amcat projects.
    Excludes system indices. Requires ADMIN server role.
    """
    await HTTPException_if_not_server_role(user, Roles.ADMIN)
    return await list_unregistered_indices()


@app_index.put("/index/{ix}", status_code=status.HTTP_204_NO_CONTENT)
async def modify_index(
    ix: Annotated[IndexId, Path(..., description="ID of the index to modify")],
    body: Annotated[UpdateIndexBody, Body(...)],
    user: User = Depends(authenticated_user),
):
    """
    Modify an existing index. Requires ADMIN role on the index.
    """
    await HTTPException_if_not_project_index_role(user, ix, Roles.ADMIN)

    try:
        await update_project_index(
            ProjectSettings(
                id=ix,
                **body.model_dump(),
            )
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Index {ix} does not exist")

    if body.guest_role:
        await set_project_guest_role(ix, Roles[body.guest_role])


@app_index.get("/index/{ix}")
async def view_index(
    request: Request, ix: IndexId = Path(..., description="ID of the index to view"), user: User = Depends(authenticated_user)
) -> IndexViewResponse:
    """
    Get details of a single index, including the user role. Requires at least OBSERVER role on the index.
    """
    try:
        d = await get_project_settings(ix)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Index {ix} does not exist")
    except Exception:
        raise HTTPException(status_code=500, detail=f"Error reading index {ix} settings")

    await HTTPException_if_not_project_index_role(user, ix, Roles.OBSERVER)
    role = await get_user_project_role(user, project_index=ix, global_admin=False)

    bytes = await index_size_in_bytes(ix)

    image_url = f"{get_settings().host}/api/index/{ix}/image/{d.image.id}" if d.image else None

    return IndexViewResponse(
        id=d.id,
        name=d.name or "",
        user_role=role.role if role else None,
        user_role_match=role.email if role else None,
        guest_role=await get_project_guest_role(d.id),
        description=d.description or "",
        archived=str(d.archived or ""),
        folder=d.folder or "",
        image_url=image_url,
        contact=d.contact or [],
        bytes=bytes,
    )


@app_index.post("/index/{ix}/archive", status_code=status.HTTP_204_NO_CONTENT)
async def archive_index(
    ix: Annotated[IndexId, Path(..., description="ID of the index to (un)archive")],
    archived: Annotated[bool, Body(..., description="Boolean for setting archived to true or false", embed=True)],
    user: User = Depends(authenticated_user),
):
    """
    Archive or unarchive the index. When an index is archived, it restricts usage, and adds a timestamp for when
    it was archived. Requires ADMIN role on the index.
    """
    await HTTPException_if_not_project_index_role(user, ix, Roles.ADMIN)
    try:
        await archive_project_index(ix, archived=archived)
    except IndexDoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} does not exist")


@app_index.delete("/index/{ix}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_index(ix: IndexId, user: User = Depends(authenticated_user)):
    """Delete the index. Requires ADMIN role on the index."""
    await HTTPException_if_not_project_index_role(user, ix, Roles.ADMIN)
    try:
        await delete_project_index(ix)
    except IndexDoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Index {ix} does not exist")


@app_index.get("/index/{ix}/refresh", status_code=status.HTTP_204_NO_CONTENT)
async def refresh(ix: str):
    """Refresh the elastic index. Use this if you need to make recently added documents searchable immediately."""
    await refresh_index(ix)


@app_index.post("/index/{ix}/reindex")
async def start_reindex(
    ix: IndexId,
    body: Annotated[ReindexBody, Body(...)],
    user: User = Depends(authenticated_user),
):
    await HTTPException_if_not_project_index_role(user, ix, Roles.READER)
    await HTTPException_if_not_project_index_role(user, body.destination, Roles.WRITER)
    filters = _standardize_filters(body.filters)

    queries = _standardize_queries(body.queries)
    return await reindex(
        source_index=ix,
        destination_index=body.destination,
        queries=queries,
        filters=filters,
        field_options={k: v.model_dump() for k, v in body.field_options.items()},
    )


@app_index.get("/index/{ix}/image/{id}")
async def get_index_image(ix: IndexId, id: str):
    """
    Get the image associated with the index. This endpoint doesn't require authentication,
    and only requires knowing the index ID and image ID.
    """

    try:
        image = await get_project_image(ix)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Index {ix} does not exist")
    except Exception:
        raise HTTPException(status_code=500, detail=f"Error reading index {ix} settings")

    if image is None or image.id != id or image.base64 is None:
        raise HTTPException(status_code=404, detail=f"Image {id} does not exist for index {ix}")

    headers = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "public, max-age=31536000, immutable",  ## browser caching for unique URLs
    }

    content = base64.b64decode(image.base64)
    return Response(content=content, media_type="image/jpeg", headers=headers)


@app_index.post("/index/{ix}/image", status_code=status.HTTP_204_NO_CONTENT)
async def upload_index_image(
    request: Request,
    ix: Annotated[IndexId, Path(..., description="ID of the index")],
    file: UploadFile = File(...),
    user: User = Depends(authenticated_user),
):
    """
    Upload an image for a project with size and type validation.
    """
    allowed_image_types = ["image/jpeg", "image/webp", "image/jpg", "image/png"]
    max_file_size = 10 * 1024 * 1024

    await HTTPException_if_not_project_index_role(user, ix, Roles.ADMIN)

    if file.content_type not in allowed_image_types:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {', '.join(allowed_image_types)}")

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > max_file_size:
        raise HTTPException(status_code=413, detail="File too large (header check)")

    full_contents = b""
    try:
        total_size = 0
        chunk_size = 1024 * 1024
        while chunk := await file.read(chunk_size):
            total_size += len(chunk)
            if total_size > max_file_size:
                await file.close()
                raise HTTPException(status_code=413, detail="File too large (stream check)")
            full_contents += chunk
    finally:
        await file.close()

    try:
        await update_project_index(
            ProjectSettings(
                id=ix,
                image=await create_image_from_bytes(full_contents),
            )
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Index {ix} does not exist")


@app_index.get("/index/{ix}/download")
async def download_index(
    ix: Annotated[IndexId, Path(..., description="ID of the index to download")],
    user: User = Depends(authenticated_user),
):
    """
    Download a complete project export as a streaming NDJSON file.
    Each line is a JSON object with a 'type' field: 'settings', 'field', 'user_role', or 'document'.
    Requires ADMIN role on the index.
    """
    await HTTPException_if_not_project_index_role(user, ix, Roles.ADMIN)

    async def generate():
        compressor = zlib.compressobj(wbits=31)  # wbits=31 = gzip format

        async def ndjson_lines():
            # 1. Project settings (image is excluded from get_project_settings, fetch separately)
            settings = await get_project_settings(ix)
            settings_dict: dict = {"_type": "settings", **settings.model_dump()}
            image = await get_project_image(ix)
            if image:
                settings_dict["image"] = image.model_dump()
            if settings_dict["archived"]:
                settings_dict["archived"] = str(settings_dict["archived"])
            yield json.dumps(settings_dict) + "\n"

            # 2. Field definitions
            fields = await list_fields(ix)
            for name, field in fields.items():
                yield json.dumps({"_type": "field", "name": name, **field.model_dump()}) + "\n"

            # 3. User roles for this project (skip NONE roles — they carry no access)
            async for role in list_project_roles(project_ids=[ix]):
                if role.role != "NONE":
                    yield json.dumps({"_type": "user_role", "email": role.email, "role": role.role}) + "\n"

            # 4. Documents via scroll
            field_specs = [FieldSpec(name=name) for name in fields]
            result = await query_documents(ix, fields=field_specs, scroll=True, per_page=500)
            while result is not None:
                for doc in result.data:
                    yield json.dumps({"_type": "document", **doc}) + "\n"
                result = await query_documents(ix, scroll_id=result.scroll_id)

        async for line in ndjson_lines():
            chunk = compressor.compress(line.encode())
            if chunk:
                yield chunk
        yield compressor.flush()

    return StreamingResponse(
        generate(),
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{ix}.ndjson.gz"'},
    )


@app_index.post("/index/import", status_code=status.HTTP_201_CREATED)
async def import_index(
    file: UploadFile = File(...),
    override_id: str | None = Query(None),
    user: User = Depends(authenticated_user),
):
    """
    Import a project from a .ndjson or .ndjson.gz file produced by the download endpoint.
    Restores project settings, fields, user roles, and documents.
    Requires WRITER or ADMIN server role.
    """
    await HTTPException_if_not_server_role(user, Roles.WRITER)

    content = await file.read()
    if content[:2] == b"\x1f\x8b":
        lines_iter = gzip.open(io.BytesIO(content), "rt", encoding="utf-8")
    else:
        lines_iter = iter(content.decode("utf-8").splitlines())

    settings_data: dict | None = None
    fields: dict[str, dict] = {}
    roles: list[dict] = []
    project_settings: ProjectSettings | None = None
    created_project_id: str | None = None
    has_identifiers = False
    n_docs = 0
    batch: list[dict] = []

    async def setup_project() -> ProjectSettings:
        nonlocal has_identifiers, created_project_id
        if settings_data is None:
            raise HTTPException(status_code=422, detail="No settings record found in file")
        sd = {**settings_data, "id": override_id} if override_id else settings_data
        ps = ProjectSettings.model_validate(sd)
        await create_project_index(ps, admin_email=user.email)
        created_project_id = ps.id
        if fields:
            field_defs = {name: CreateDocumentField.model_validate(f) for name, f in fields.items()}
            await create_fields(ps.id, field_defs)
        has_identifiers = any(f.get("identifier") for f in fields.values())
        for role in roles:
            if Roles[role["role"]] == Roles.NONE:
                continue
            try:
                await create_project_role(role["email"], ps.id, Roles[role["role"]])
            except ConflictError:
                await update_project_role(role["email"], ps.id, Roles[role["role"]])
        return ps

    try:
        for raw_line in lines_iter:
            line = raw_line.strip()
            if not line:
                continue
            obj = json.loads(line)
            record_type = obj.pop("_type", None)
            if record_type == "settings":
                settings_data = obj
            elif record_type == "field":
                name = obj.pop("name")
                fields[name] = obj
            elif record_type == "user_role":
                roles.append(obj)
            elif record_type == "document":
                if project_settings is None:
                    project_settings = await setup_project()
                doc = {k: v for k, v in obj.items() if k != "_id"} if has_identifiers else obj
                batch.append(doc)
                n_docs += 1
                if len(batch) >= 500:
                    await create_or_update_documents(project_settings.id, batch)
                    batch = []

        if project_settings is None:
            project_settings = await setup_project()
        if batch:
            await create_or_update_documents(project_settings.id, batch)

    except IndexAlreadyExists as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception:
        if created_project_id is not None:
            await delete_project_index(created_project_id, ignore_missing=True)
        raise

    return {"project_id": project_settings.id, "n_fields": len(fields), "n_roles": len(roles), "n_documents": n_docs}
