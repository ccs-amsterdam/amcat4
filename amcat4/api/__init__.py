"""AmCAT4 API."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from amcat4.api.index import app_index
from amcat4.api.index_documents import app_index_documents
from amcat4.api.index_fields import app_index_fields
from amcat4.api.index_multimedia import app_multimedia
from amcat4.api.index_query import app_index_query
from amcat4.api.index_users import app_index_users
from amcat4.api.info import app_info
from amcat4.api.requests import app_requests
from amcat4.api.users import app_users
from amcat4.connections import close_amcat_connections, start_amcat_connections
from amcat4.systemdata.manage import create_or_update_systemdata


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Initializing system data...")
    await start_amcat_connections()
    await create_or_update_systemdata()

    yield
    ## cleanup should happen here
    await close_amcat_connections()


app = FastAPI(
    title="AmCAT4",
    description=__doc__ if __doc__ else "",
    openapi_tags=[
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
    ],
    lifespan=lifespan,
)
app.include_router(app_info)
app.include_router(app_users)
app.include_router(app_index)
app.include_router(app_index_documents)
app.include_router(app_index_fields)
app.include_router(app_index_users)
app.include_router(app_index_query)
app.include_router(app_requests)
app.include_router(app_multimedia)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.exception_handler(ValueError)
async def value_error_exception_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"message": str(exc)},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc) -> JSONResponse:
    return JSONResponse(
        status_code=422, content={"message": "There was an issue with the data you sent.", "fields_invalid": exc.errors()}
    )
