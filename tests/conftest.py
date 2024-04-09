from typing import Any
import pytest
import responses
from fastapi.testclient import TestClient

from amcat4 import api  # noqa: E402
from amcat4.config import get_settings, AuthOptions
from amcat4.elastic import es
from amcat4.index import (
    create_index,
    delete_index,
    Role,
    refresh_index,
    delete_user,
    remove_global_role,
    set_global_role,
    upload_documents,
)
from amcat4.models import CreateField, ElasticType, FieldType
from tests.middlecat_keypair import PUBLIC_KEY

UNITS = [
    {"unit": {"text": "unit1"}},
    {"unit": {"text": "unit2"}, "gold": {"element": "au"}},
]
CODEBOOK = {"foo": "bar"}
PROVENANCE = {"bar": "foo"}
RULES = {"ruleset": "crowdcoding"}
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

    es.cache_clear()
    yield None
    delete_index(UNITTEST_SYSTEM_INDEX, ignore_missing=True)


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
    set_global_role(email, Role.ADMIN)
    yield email
    remove_global_role(email)


@pytest.fixture()
def writer():
    email = "writer@amcat.nl"
    set_global_role(email, Role.WRITER)
    yield email
    remove_global_role(email)


@pytest.fixture()
def reader():
    email = "reader@amcat.nl"
    set_global_role(email, Role.READER)
    yield email
    remove_global_role(email)


@pytest.fixture()
def writer2():
    email = "writer2@amcat.nl"
    set_global_role(email, Role.WRITER)
    yield email
    remove_global_role(email)


@pytest.fixture()
def user():
    name = "test_user@amcat.nl"
    delete_user(name)
    set_global_role(name, Role.READER)
    yield name
    delete_user(name)


@pytest.fixture()
def username():
    """A name to create a user which will be deleted afterwards if needed"""
    name = "test_username@amcat.nl"
    delete_user(name)
    yield name
    delete_user(name)


@pytest.fixture()
def index():
    index = "amcat4_unittest_index"
    delete_index(index, ignore_missing=True)
    create_index(index)
    yield index
    delete_index(index, ignore_missing=True)


@pytest.fixture()
def index_name():
    """An index name that is guaranteed not to exist and will be cleaned up after the test"""
    index = "amcat4_unittest_indexname"
    delete_index(index, ignore_missing=True)
    yield index
    delete_index(index, ignore_missing=True)


@pytest.fixture()
def guest_index():
    index = "amcat4_unittest_guest_index"
    delete_index(index, ignore_missing=True)
    create_index(index, guest_role=Role.READER)
    yield index
    delete_index(index, ignore_missing=True)


def upload(index: str, docs: list[dict[str, Any]], fields: dict[str, FieldType | CreateField] | None = None):
    """
    Upload these docs to the index, giving them an incremental id, and flush
    """
    res = upload_documents(index, docs, fields)
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
    delete_index(index, ignore_missing=True)
    create_index(index, guest_role=Role.READER)
    populate_index(index)
    yield index
    delete_index(index, ignore_missing=True)


@pytest.fixture()
def index_many():
    index = "amcat4_unittest_indexmany"
    delete_index(index, ignore_missing=True)
    create_index(index, guest_role=Role.READER)
    upload(
        index,
        [dict(id=i, pagenr=abs(10 - i), text=text) for (i, text) in enumerate(["odd", "even"] * 10)],
        fields={"id": "integer", "pagenr": "integer", "text": "text"},
    )
    yield index
    delete_index(index, ignore_missing=True)


@pytest.fixture()
def app():
    return api.app
