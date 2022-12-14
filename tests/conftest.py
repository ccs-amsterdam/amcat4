from typing import Iterable

import pytest
from elasticsearch.exceptions import NotFoundError

from fastapi.testclient import TestClient

from amcat4 import elastic, api  # noqa: E402
from amcat4.config import get_settings
from amcat4.elastic import es
from amcat4.index import create_index, delete_index, Role, set_role, remove_role, refresh

UNITS = [{"unit": {"text": "unit1"}},
         {"unit": {"text": "unit2"}, "gold": {"element": "au"}}]
CODEBOOK = {"foo": "bar"}
PROVENANCE = {"bar": "foo"}
RULES = {"ruleset": "crowdcoding"}
UNITTEST_SYSTEM_INDEX = "amcat4_unittest_system"


@pytest.fixture(scope="session", autouse=True)
def my_setup():
    # Override system db
    get_settings().system_index = UNITTEST_SYSTEM_INDEX
    es.cache_clear()
    yield None
    es().indices.delete(index=UNITTEST_SYSTEM_INDEX, ignore=[404])


@pytest.fixture()
def client():
    return TestClient(api.app)


@pytest.fixture()
def user():
    u = create_user(email="testuser@test.com", password="test")
    u.plaintext_password = "test"
    yield u
    u.delete_instance()


@pytest.fixture()
def writer():
    u = create_user(email="writer@test.com", password="test", global_role=Role.WRITER)
    u.plaintext_password = "test"
    yield u
    u.delete_instance()


@pytest.fixture()
def admin():
    email = "admin@example.com"
    set_role(email, Role.ADMIN)
    yield email
    remove_role(email)


@pytest.fixture()
def index():
    index = "amcat4_unittest_index"
    delete_index(index, ignore_missing=True)
    create_index(index)
    yield index
    delete_index(index, ignore_missing=True)


@pytest.fixture()
def guest_index():
    index = "amcat4_unittest_guest_index"
    delete_index(index, ignore_missing=True)
    create_index(index, guest_role=Role.READER)
    yield index
    delete_index(index, ignore_missing=True)


def upload(index: str, docs: Iterable[dict], **kwargs):
    """
    Upload these docs to the index, giving them an incremental id, and flush
    """
    ids = []
    for i, doc in enumerate(docs):
        id = str(i)
        ids.append(id)
        defaults = {'title': "title", 'date': "2018-01-01", 'text': "text", '_id': id}
        for k, v in defaults.items():
            if k not in doc:
                doc[k] = v
    elastic.upload_documents(index, docs, **kwargs)
    refresh(index)
    return ids


TEST_DOCUMENTS = [
    {'cat': 'a', 'subcat': 'x', 'i': 1, 'date': '2018-01-01', 'text': 'this is a text', },
    {'cat': 'a', 'subcat': 'x', 'i': 2, 'date': '2018-02-01', 'text': 'a test text', },
    {'cat': 'a', 'subcat': 'y', 'i': 11, 'date': '2020-01-01', 'text': 'and this is another test toto', 'title': 'bla'},
    {'cat': 'b', 'subcat': 'y', 'i': 31, 'date': '2018-01-01', 'text': 'Toto je testovací článek', 'title': 'more bla'},
]


def populate_index(index):
    upload(index, TEST_DOCUMENTS, fields={'cat': 'keyword', 'subcat': 'keyword', 'i': 'long'})
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
    upload(index, [dict(id=i, pagenr=abs(10 - i), text=text) for (i, text) in enumerate(["odd", "even"] * 10)])
    yield index
    delete_index(index, ignore_missing=True)


@pytest.fixture()
def index_name():
    """A name to create an index which will be deleted afterwards if needed"""
    name = "amcat4_unittest_index_name"
    delete_index(index, ignore_missing=True)
    yield name
    delete_index(index, ignore_missing=True)


@pytest.fixture()
def username():
    """A name to create a user which will be deleted afterwards if needed"""
    setup_elastic()
    name = "test_user@test.com"
    yield name
    u = User.get_or_none(User.email == name)
    if u:
        u.delete_instance()


@pytest.fixture()
def app():
    return api.app
