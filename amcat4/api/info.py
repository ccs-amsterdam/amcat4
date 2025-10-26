"""API Endpoints for server information and configuration."""

from importlib.metadata import version

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from amcat4.api.auth import authenticated_user, get_middlecat_config
from amcat4.config import get_settings, validate_settings
from amcat4.elastic.connection import connect_elastic
from amcat4.projects.query import get_task_status
from amcat4.models import Roles, ServerSettings, User
from amcat4.systemdata.roles import HTTPException_if_not_server_role
from amcat4.systemdata.settings import upsert_server_settings, get_server_settings

templates = Jinja2Templates(directory="templates")

app_info = APIRouter(tags=["informational"])


# RESPONSE MODELS
class AuthConfigResponse(BaseModel):
    """Response for authentication configuration."""

    middlecat_url: str | None = Field(None, description="The URL of the MiddleCat server.")
    resource: str | None = Field(None, description="The resource identifier for this AmCAT instance.")
    authorization: str = Field(..., description="The authorization mode.")
    warnings: list[str] = Field(..., description="A list of configuration warnings.")
    minio: bool = Field(..., description="Whether MinIO is configured.")
    api_version: str = Field(..., description="The version of the AmCAT API.")


class TaskStatusResponse(BaseModel):
    """Response for a background task status."""

    status: str = Field(..., description="The status of the task.")
    progress: int = Field(..., description="The progress of the task in percent.")
    message: str | None = Field(None, description="A message about the task status.")
    result: dict | None = Field(None, description="The result of the task if completed.")


@app_info.get("/")
def index(request: Request):
    """Returns an HTML page with information about this AmCAT instance."""
    host = get_settings().host
    es_alive = connect_elastic().ping()
    auth = get_settings().auth
    has_admin_email = bool(get_settings().admin_email)
    middlecat_url = get_settings().middlecat_url

    middlecat_alive = False
    api_version = version("amcat4")
    if middlecat_url:
        try:
            get_middlecat_config(middlecat_url)
            # middlecat_alive = True
        except OSError:
            pass
    return templates.TemplateResponse("index.html", locals())


@app_info.get("/config")
@app_info.get("/middlecat")
def get_auth_config() -> AuthConfigResponse:
    """Get the authentication configuration for this AmCAT instance."""
    settings = get_settings()
    return {
        "middlecat_url": settings.middlecat_url,
        "resource": settings.host,
        "authorization": settings.auth,
        "warnings": [w for w in [validate_settings()] if w],
        "minio": settings.minio_host != "None",
        "api_version": version("amcat4"),
    }


@app_info.get("/config/branding")
def read_branding() -> ServerSettings:
    """Get the server branding settings."""
    return get_server_settings()


@app_info.put("/config/branding", status_code=status.HTTP_204_NO_CONTENT)
def change_branding(data: ServerSettings, user: User = Depends(authenticated_user)):
    """Update the server branding settings. Requires ADMIN server role."""
    HTTPException_if_not_server_role(user, Roles.ADMIN)
    upsert_server_settings(data)


@app_info.get("/task/{taskId}")
def task_status(taskId: str, _user: User = Depends(authenticated_user)) -> TaskStatusResponse:
    """Get the status of a background task."""
    return get_task_status(taskId)
