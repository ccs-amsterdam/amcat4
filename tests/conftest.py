import asyncio
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from amcat4 import api
from amcat4.config import AuthOptions, get_settings
from amcat4.connections import amcat_connections, es
from amcat4.models import CreateDocumentField, FieldType, ProjectSettings, Roles
from amcat4.projects.documents import create_or_update_documents
from amcat4.projects.index import create_project_index, delete_project_index, refresh_index
from amcat4.systemdata.manage import create_or_update_systemdata, delete_systemdata_version
from amcat4.systemdata.requests import clear_requests
from amcat4.systemdata.roles import (
    delete_server_role,
    set_project_guest_role,
    update_server_role,
)
from tests.middlecat_keypair import PUBLIC_KEY

AMCAT_TESTS_PREFIX = "amcat4_unittest"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session")
async def client():
    async with AsyncClient(transport=ASGITransport(app=api.app), base_url="http://test", follow_redirects=False) as client:
        yield client


@pytest.fixture(scope="session", autouse=True)
async def my_setup():
    # Override system db
    get_settings().auth = AuthOptions.allow_guests
    get_settings().use_test_db = True

    async with amcat_connections():
        systemdata_version = await create_or_update_systemdata()
        yield
        await delete_systemdata_version(systemdata_version)


@pytest.fixture(autouse=True)
def mock_middlecat(httpx_mock):
    get_settings().middlecat_url = "http://mock_middlecat.net"
    get_settings().host = "http://localhost:3000"

    httpx_mock.add_response(
        url="http://mock_middlecat.net/api/configuration", method="GET", json={"public_key": PUBLIC_KEY}, is_optional=True
    )


def not_localhost(request):
    """
    For test that need to make calls to localhost (e.g., s3 presigned urls),
    and bypass the httpx_mock for those requests, add this decorator

    @pytest.mark.httpx_mock(should_mock=not_localhost)
    """
    return request.url.host != "localhost"


@pytest.fixture(scope="function")
async def admin():
    email = "admin@amcat.nl"
    await update_server_role(email, Roles.ADMIN, ignore_missing=True)
    yield email
    await delete_server_role(email, ignore_missing=True)


@pytest.fixture(scope="function")
async def writer():
    email = "writer@amcat.nl"
    await update_server_role(email, Roles.WRITER, ignore_missing=True)
    yield email
    await delete_server_role(email, ignore_missing=True)


@pytest.fixture(scope="function")
async def reader():
    email = "reader@amcat.nl"
    await update_server_role(email, Roles.READER, ignore_missing=True)
    yield email
    await delete_server_role(email, ignore_missing=True)


@pytest.fixture(scope="function")
async def writer2():
    email = "writer2@amcat.nl"
    await update_server_role(email, Roles.WRITER, ignore_missing=True)
    yield email
    await delete_server_role(email, ignore_missing=True)


@pytest.fixture(scope="function")
async def user():
    email = "test_user@amcat.nl"
    await update_server_role(email, Roles.READER, ignore_missing=True)
    yield email
    await delete_server_role(email, ignore_missing=True)


@pytest.fixture(scope="function")
async def username():
    """A name to create a user which will be deleted afterwards if needed"""
    email = "test_username@amcat.nl"
    await delete_server_role(email, ignore_missing=True)
    yield email
    await delete_server_role(email, ignore_missing=True)


@pytest.fixture(scope="function")
async def index():
    index = "amcat4_unittest_index"
    await delete_project_index(index, ignore_missing=True)
    await create_project_index(ProjectSettings(id=index, name="Unittest Index"))
    yield index
    await delete_project_index(index, ignore_missing=True)


@pytest.fixture(scope="function")
async def index_name():
    """An index name that is guaranteed not to exist and will be cleaned up after the test"""
    index = "amcat4_unittest_indexname"
    await delete_project_index(index, ignore_missing=True)
    yield index
    await delete_project_index(index, ignore_missing=True)


@pytest.fixture(scope="function")
async def guest_index():
    index = "amcat4_unittest_guest_index"
    await delete_project_index(index, ignore_missing=True)
    await create_project_index(ProjectSettings(id=index))
    await set_project_guest_role(index, Roles.READER)
    yield index
    await delete_project_index(index, ignore_missing=True)


@pytest.fixture(scope="function")
async def clean_requests():
    """Clean up requests before and after the test"""
    await clear_requests()
    yield
    await clear_requests()


# @pytest.fixture()
# async def index_with_multimedia():
#     if not s3_enabled():
#         pytest.skip("S3 not configured, skipping tests needing object storage")

#     index = "amcat4_unittest_index_bucket"
#     await delete_project_index(index, ignore_missing=True)
#     await delete_project_multimedia(index)
#     await create_project_index(ProjectSettings(id=index, name="Unittest Index"))
#     yield index
#     # await delete_project_index(index, ignore_missing=True)
#     # await delete_index_bucket(index, ignore_missing=True)


async def upload(index: str, docs: list[dict[str, Any]], fields: dict[str, FieldType | CreateDocumentField] | None = None):
    """
    Upload these docs to the index, giving them an incremental id, and flush
    """
    await create_or_update_documents(index, docs, fields)
    await refresh_index(index)


TEST_DOCUMENTS = [
    {"_id": 0, "cat": "a", "subcat": "x", "i": 1, "date": "2018-01-01", "text": "this is a text", "title": "title"},
    {"_id": 1, "cat": "a", "subcat": "x", "i": 2, "date": "2018-02-01", "text": "a test text", "title": "title"},
    {
        "_id": 2,
        "cat": "a",
        "subcat": "y",
        "i": 11,
        "date": "2020-01-01",
        "text": "and this is another test toto",
        "title": "bla",
    },
    {
        "_id": 3,
        "cat": "b",
        "subcat": "y",
        "i": 31,
        "date": "2018-01-01",
        "text": "Toto je testovací článek",
        "title": "more bla",
    },
]


async def populate_index(index):
    await upload(
        index,
        TEST_DOCUMENTS,
        fields={
            "text": "text",
            "title": "text",
            "date": "date",
            "cat": "keyword",
            "subcat": "keyword",
            "i": "integer",
        },
    )
    return TEST_DOCUMENTS


@pytest.fixture(scope="function")
async def index_docs():
    index = "amcat4_unittest_indexdocs"
    await delete_project_index(index, ignore_missing=True)
    await create_project_index(ProjectSettings(id=index, name="Unittest Index with Docs"))
    await populate_index(index)
    yield index
    await delete_project_index(index, ignore_missing=True)


@pytest.fixture(scope="function")
async def index_many():
    index = "amcat4_unittest_indexmany"
    await delete_project_index(index, ignore_missing=True)
    await create_project_index(ProjectSettings(id=index))
    await set_project_guest_role(index, Roles.READER)
    await upload(
        index,
        [dict(id=i, pagenr=abs(10 - i), text=text) for (i, text) in enumerate(["odd", "even"] * 10)],
        fields={"id": "integer", "pagenr": "integer", "text": "text"},
    )
    yield index
    await delete_project_index(index, ignore_missing=True)


@pytest.fixture(scope="function")
def app():
    return api.app
