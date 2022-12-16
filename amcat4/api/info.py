from fastapi import Request
from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

from amcat4 import elastic
from amcat4.config import get_settings

templates = Jinja2Templates(directory="templates")

app_info = APIRouter(
    tags=["informational"])


@app_info.get("/")
def index(request: Request):
    host = get_settings().host

    es_alive = elastic.ping()
    has_admin = bool(get_settings().admin_password)
    middlecat_url = get_settings().middlecat_url
    return templates.TemplateResponse("index.html", locals())
