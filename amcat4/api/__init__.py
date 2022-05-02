"""
AmCAT4 API
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from amcat4.api.index import app_index
from amcat4.api.query import app_query
from amcat4.api.users import app_users
from amcat4.db import initialize_if_needed
from amcat4.elastic import setup_elastic



app = FastAPI(
    title="AmCAT4",
    description=__doc__,
    openapi_tags=[
        dict(name="users", description="Endpoints for user management"),
        dict(name="index", description="Endpoints to create, list, and delete indices; and to add or modify documents"),
        dict(name="query", description="Endpoints to list or query documents or run aggregate queries")
    ]

)
app.include_router(app_users)
app.include_router(app_index)
app.include_router(app_query)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def init():
    setup_elastic()
    initialize_if_needed()

# "Plugins"
# app.register_blueprint(app_annotator, url_prefix='/annotator')
