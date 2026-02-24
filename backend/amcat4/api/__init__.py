"""AmCAT4 API."""

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from amcat4.api.api_keys import app_api_keys
from amcat4.api.auth import app_auth
from amcat4.api.index import app_index
from amcat4.api.index_documents import app_index_documents
from amcat4.api.index_fields import app_index_fields
from amcat4.api.index_multimedia import app_multimedia
from amcat4.api.index_query import app_index_query
from amcat4.api.index_users import app_index_users
from amcat4.api.requests import app_requests
from amcat4.api.server import app_info
from amcat4.api.users import app_users
from amcat4.auth.CSRFMiddleware import CSRFMiddleware
from amcat4.config import get_settings
from amcat4.connections import amcat_connections
from amcat4.systemdata.manage import create_or_update_systemdata


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Initializing system data...")
    async with amcat_connections():
        await create_or_update_systemdata()
        yield


app = FastAPI(
    title="AmCAT4",
    description=__doc__ if __doc__ else "",
    openapi_tags=[
        dict(name="auth", description="Endpoints for authentication"),
        dict(name="users", description="Endpoints for server user management"),
        dict(name="requests", description="Endpoints for authorization requests"),
        dict(
            name="index",
            description="Endpoints to create, list, and delete indices",
        ),
        dict(name="documents", description="Endpoints to upload, retrieve, modify, and delete documents"),
        dict(name="project users", description="Endpoints for project user management"),
        dict(name="project fields", description="Endpoints to list, create, and modify project index fields"),
        dict(name="query", description="Endpoints to list or query documents or run aggregate queries"),
        dict(name="middlecat", description="MiddleCat authentication"),
        dict(name="api keys", description="Endpoints for API key management"),
    ],
    lifespan=lifespan,
)

api_router = APIRouter()
api_router.include_router(app_auth)
api_router.include_router(app_info)
api_router.include_router(app_users)
api_router.include_router(app_index)
api_router.include_router(app_index_documents)
api_router.include_router(app_index_fields)
api_router.include_router(app_index_users)
api_router.include_router(app_index_query)
api_router.include_router(app_requests)
api_router.include_router(app_multimedia)
api_router.include_router(app_api_keys)
app.include_router(api_router)

## TODO: figure out what's best here.
# Ideally we disable CORS, and only allow own origin. But middlecat currently
# fetches the server config, and does this via the browser, because if it does
# it via the server it doesn't work for local amcat servers. Maybe we can
# disable this call altogether when we simplify middlecat for the new situation
# (tight integration ui and amcat api)
app.add_middleware(CORSMiddleware, allow_origins=["https://middlecat.net"])

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().cookie_secret,
    session_cookie="amcat_session",
    same_site="lax",
    https_only=True,  # Ensure this is True in production
)

app.add_middleware(CSRFMiddleware)


@app.exception_handler(ValueError)
async def value_error_exception_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"message": str(exc)},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc) -> JSONResponse:
    return JSONResponse(
        status_code=422, content={"message": "There was an issue with the data you sent.", "detail": exc.errors()}
    )
