from importlib.metadata import version

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from amcat4.api.auth import authenticated_user, get_middlecat_config
from amcat4.config import get_settings, validate_settings
from amcat4.elastic.connection import connect_elastic
from amcat4.projects.query import get_task_status
from amcat4.models import Roles, ServerSettings, User
from amcat4.systemdata.roles import raise_if_not_server_role
from amcat4.systemdata.settings import upsert_server_settings, get_server_settings

templates = Jinja2Templates(directory="templates")

app_info = APIRouter(tags=["informational"])


@app_info.get("/")
def index(request: Request):
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
def get_auth_config():
    print(get_settings())
    return {
        "middlecat_url": get_settings().middlecat_url,
        "resource": get_settings().host,
        "authorization": get_settings().auth,
        "warnings": [validate_settings()],
        "minio": get_settings().minio_host != "None",
        "api_version": version("amcat4"),
    }


@app_info.get("/config/branding")
def read_branding():
    return get_server_settings()


@app_info.put("/config/branding")
def change_branding(data: ServerSettings, user: User = Depends(authenticated_user)):
    ## This doesn't yet make sense. The problem is that if we have a separate branding endpoint,
    ## we need to make sure that the server_settings document exists.
    raise_if_not_server_role(user, Roles.ADMIN)
    upsert_server_settings(data)


@app_info.get("/task/{taskId}")
def task_status(taskId: str, _user: User = Depends(authenticated_user)):
    return get_task_status(taskId)
