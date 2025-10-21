from typing import Any
import pytest
import responses
from fastapi.testclient import TestClient

from amcat4 import api
from amcat4.config import get_settings, AuthOptions
from amcat4.elastic import es
from amcat4.models import CreateField, FieldType, ProjectSettings, Roles
from amcat4.projects.documents import upload_documents
from amcat4.projects.index import create_project_index, delete_project_index, refresh_index
from amcat4.systemdata.manage import create_or_update_systemdata, delete_systemdata_version
from amcat4.systemdata.requests import clear_requests
from amcat4.systemdata.roles import (
    delete_server_role,
    set_project_guest_role,
    update_server_role,
)
from tests.middlecat_keypair import PUBLIC_KEY

UNITTEST_SYSTEM_INDEX = "amcat4_unittest_system"


@pytest.fixture(scope="session", autouse=True)
def mock_middlecat():
    get_settings().middlecat_url = "http://localhost:5000"
    get_settings().host = "http://localhost:3000"
    with responses.RequestsMock(assert_all_requests_are_fired=False) as resp:
        resp.get("http://localhost:5000/api/configuration", json={"public_key": PUBLIC_KEY})
        yield None


@pytest.fixture(scope="session", autouse=True)
def my_setup():
    # Override system db
    get_settings().system_index = UNITTEST_SYSTEM_INDEX
    system_index_version = create_or_update_systemdata(rm_broken_versions=True)

    es.cache_clear()
    yield None
    delete_systemdata_version(system_index_version)


@pytest.fixture(scope="session", autouse=True)
def default_settings():
    # Set default settings so tests are free to change the auth setting
    get_settings().auth = AuthOptions.allow_guests


@pytest.fixture()
def client():
    return TestClient(api.app)


@pytest.fixture()
def admin():
    email = "admin@amcat.nl"
    update_server_role(email, Roles.ADMIN, ignore_missing=True)
    yield email
    delete_server_role(email, ignore_missing=True)


@pytest.fixture()
def writer():
    email = "writer@amcat.nl"
    update_server_role(email, Roles.WRITER, ignore_missing=True)
    yield email
    delete_server_role(email, ignore_missing=True)


@pytest.fixture()
def reader():
    email = "reader@amcat.nl"
    update_server_role(email, Roles.READER, ignore_missing=True)
    yield email
    delete_server_role(email, ignore_missing=True)


@pytest.fixture()
def writer2():
    email = "writer2@amcat.nl"
    update_server_role(email, Roles.WRITER, ignore_missing=True)
    yield email
    delete_server_role(email, ignore_missing=True)


@pytest.fixture()
def user():
    email = "test_user@amcat.nl"
    update_server_role(email, Roles.READER, ignore_missing=True)
    yield email
    delete_server_role(email, ignore_missing=True)


@pytest.fixture()
def username():
    """A name to create a user which will be deleted afterwards if needed"""
    email = "test_username@amcat.nl"
    delete_server_role(email, ignore_missing=True)
    yield email
    delete_server_role(email, ignore_missing=True)


@pytest.fixture()
def index():
    index = "amcat4_unittest_index"
    delete_project_index(index, ignore_missing=True)
    create_project_index(ProjectSettings(id=index, name="Unittest Index"))
    yield index
    delete_project_index(index, ignore_missing=True)


@pytest.fixture()
def index_name():
    """An index name that is guaranteed not to exist and will be cleaned up after the test"""
    index = "amcat4_unittest_indexname"
    delete_project_index(index, ignore_missing=True)
    yield index
    delete_project_index(index, ignore_missing=True)


@pytest.fixture()
def guest_index():
    index = "amcat4_unittest_guest_index"
    delete_project_index(index, ignore_missing=True)
    create_project_index(ProjectSettings(id=index))
    set_project_guest_role(index, Roles.READER)
    yield index
    delete_project_index(index, ignore_missing=True)


@pytest.fixture()
def clean_requests():
    """Clean up requests before and after the test"""
    clear_requests()
    yield
    clear_requests()


def upload(index: str, docs: list[dict[str, Any]], fields: dict[str, FieldType | CreateField] | None = None):
    """
    Upload these docs to the index, giving them an incremental id, and flush
    """
    upload_documents(index, docs, fields)
    refresh_index(index)


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


def populate_index(index):
    upload(
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


@pytest.fixture()
def index_docs():
    index = "amcat4_unittest_indexdocs"
    delete_project_index(index, ignore_missing=True)
    create_project_index(ProjectSettings(id=index, name="Unittest Index with Docs"))
    populate_index(index)
    yield index
    delete_project_index(index, ignore_missing=True)


@pytest.fixture()
def index_many():
    index = "amcat4_unittest_indexmany"
    delete_project_index(index, ignore_missing=True)
    create_project_index(ProjectSettings(id=index))
    set_project_guest_role(index, Roles.READER)
    upload(
        index,
        [dict(id=i, pagenr=abs(10 - i), text=text) for (i, text) in enumerate(["odd", "even"] * 10)],
        fields={"id": "integer", "pagenr": "integer", "text": "text"},
    )
    yield index
    delete_project_index(index, ignore_missing=True)


@pytest.fixture()
def app():
    return api.app
