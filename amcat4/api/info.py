from importlib.metadata import version

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from amcat4 import elastic
from amcat4.api.auth import authenticated_admin, get_middlecat_config
from amcat4.config import get_settings, validate_settings
from amcat4.index import get_branding, set_branding

templates = Jinja2Templates(directory="templates")

app_info = APIRouter(tags=["informational"])


@app_info.get("/")
def index(request: Request):
    host = get_settings().host
    es_alive = elastic.ping()
    auth = get_settings().auth
    has_admin_email = bool(get_settings().admin_email)
    middlecat_url = get_settings().middlecat_url
    middlecat_alive = False
    api_version = version("amcat4")
    if middlecat_url:
        try:
            get_middlecat_config(middlecat_url)
            middlecat_alive = True
        except OSError:
            pass
    return templates.TemplateResponse("index.html", locals())


@app_info.get("/config")
@app_info.get("/middlecat")
def get_auth_config():
    return {
        "middlecat_url": get_settings().middlecat_url,
        "resource": get_settings().host,
        "authorization": get_settings().auth,
        "warnings": [validate_settings()],
        "api_version": version("amcat4"),
    }


@app_info.get("/config/branding")
def read_branding():
    return get_branding()


class ChangeBranding(BaseModel):
    server_name: str | None = None
    server_icon: str | None = None
    server_url: str | None = None
    welcome_text: str | None = None
    client_data: str | None = None


@app_info.put("/config/branding")
def change_branding(data: ChangeBranding, user: str = Depends(authenticated_admin)):
    set_branding(
        server_icon=data.server_icon,
        server_name=data.server_name,
        welcome_text=data.welcome_text,
        client_data=data.client_data,
        server_url=data.server_url,
    )
