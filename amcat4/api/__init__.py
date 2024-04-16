"""AmCAT4 API."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from amcat4.api.index import app_index
from amcat4.api.info import app_info
from amcat4.api.query import app_query
from amcat4.api.users import app_users
from amcat4.api.multimedia import app_multimedia
from amcat4.api.preprocessing import app_preprocessing


app = FastAPI(
    title="AmCAT4",
    description=__doc__,
    openapi_tags=[
        dict(name="users", description="Endpoints for user management"),
        dict(name="index", description="Endpoints to create, list, and delete indices; and to add or modify documents"),
        dict(name="query", description="Endpoints to list or query documents or run aggregate queries"),
        dict(name="middlecat", description="MiddleCat authentication"),
        dict(name="annotator users", description="Annotator module endpoints for user management"),
        dict(
            name="annotator codingjob",
            description="Annotator module endpoints for creating and managing annotator codingjobs, "
            "and the core process of getting units and posting annotations",
        ),
        dict(name="annotator guest", description="Annotator module endpoints for unregistered guests"),
        dict(name="multimedia", description="Endpoints for multimedia support"),
        dict(name="preprocessing", description="Endpoints for preprocessing support"),
    ],
)
app.include_router(app_info)
app.include_router(app_users)
app.include_router(app_index)
app.include_router(app_query)
app.include_router(app_multimedia)
app.include_router(app_preprocessing)
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
