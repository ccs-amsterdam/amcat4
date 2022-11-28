from fastapi import Request
from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

app_info = APIRouter(
    tags=["informational"])


@app_info.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "id": 1})
