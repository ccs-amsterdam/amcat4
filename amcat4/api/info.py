"""API Endpoints for server information and configuration."""

from importlib.metadata import version

from fastapi import APIRouter, Depends, Request, status
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from amcat4.api.auth import authenticated_user, get_middlecat_config
from amcat4.config import get_settings, validate_settings
from amcat4.elastic.connection import connect_elastic
from amcat4.multimedia.objectstorage import s3_enabled
from amcat4.projects.query import get_task_status
from amcat4.models import ContactInfo, Links, LinksGroup, Roles, ServerSettings, User
from amcat4.multimedia.image_processing import create_image_from_url
from amcat4.systemdata.roles import HTTPException_if_not_server_role
from amcat4.systemdata.settings import upsert_server_settings, get_server_settings

templates = Jinja2Templates(directory="templates")

app_info = APIRouter(tags=["informational"])


class BrandingBody(BaseModel):
    name: str | None = Field(None, description="The name of the server.")
    description: str | None = Field(None, description="A description of the server.")
    contact: list[ContactInfo] | None = Field(None, description="Contact information for the server admins.")
    external_url: str | None = Field(None, description="The external URL of the server.")
    welcome_text: str | None = Field(None, description="Welcome text for the server.")
    information_links: list[LinksGroup] | None = Field(None, description="Information links for the server.")
    welcome_buttons: list[Links] | None = Field(None, description="Welcome buttons for the server.")


class UpdateBrandingBody(BaseModel):
    icon_url: str | None = Field(None, description="Icon image url for the server.")


class BrandingResponse(BaseModel):
    icon_id: str | None = Field(None, description="The ID of the server icon image.")


# RESPONSE MODELS
class AuthConfigResponse(BaseModel):
    """Response for authentication configuration."""

    middlecat_url: str | None = Field(None, description="The URL of the MiddleCat server.")
    resource: str | None = Field(None, description="The resource identifier for this AmCAT instance.")
    authorization: str = Field(..., description="The authorization mode.")
    warnings: list[str] = Field(..., description="A list of configuration warnings.")
    s3_enabled: bool = Field(..., description="Whether S3 storage is configured.")
    api_version: str = Field(..., description="The version of the AmCAT API.")


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

    return AuthConfigResponse(
        middlecat_url=settings.middlecat_url,
        resource=settings.host,
        authorization=settings.auth,
        warnings=[w for w in [validate_settings()] if w],
        s3_enabled=s3_enabled(),
        api_version=version("amcat4"),
    )


@app_info.get("/config/branding")
def read_branding() -> BrandingResponse:
    """Get the server branding settings."""
    settings = get_server_settings()
    d = settings.model_dump(exclude={"icon"})
    d["icon_id"] = settings.icon.id if settings.icon else None
    return BrandingResponse(**d)


@app_info.put("/config/branding", status_code=status.HTTP_204_NO_CONTENT)
def change_branding(data: UpdateBrandingBody, user: User = Depends(authenticated_user)):
    """Update the server branding settings. Requires ADMIN server role."""
    HTTPException_if_not_server_role(user, Roles.ADMIN)
    d = data.model_dump(exclude_unset=True, exclude={"icon_url"})
    d["icon"] = create_image_from_url(data.icon_url) if data.icon_url else None
    upsert_server_settings(ServerSettings(**d))


@app_info.get("/task/{taskId}")
def task_status(taskId: str, _user: User = Depends(authenticated_user)):
    """Get the status of a background task."""
    return get_task_status(taskId)
