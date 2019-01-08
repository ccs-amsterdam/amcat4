import random
import string

from nose.tools import assert_equal

from amcat4.elastic import create_project, list_projects, delete_project, upload_documents, _get_hash, get_document


def test_create_delete_list_project():
    name = '__test__create_' + ''.join(random.choices(string.ascii_lowercase, k=32))
    try:
        assert name not in list_projects()
        create_project(name)
        assert name in list_projects()
        delete_project(name)
        assert name not in list_projects()
    finally:
        delete_project(name, ignore_missing=True)


_TEST_PROJECT = '__test__' + ''.join(random.choices(string.ascii_lowercase, k=32))


def setup_module():
    create_project(_TEST_PROJECT)


def teardown_module():
    delete_project(_TEST_PROJECT, ignore_missing=True)


def test_upload_retrieve_document():
    a = dict(text="text", title="title", date="2018-01-01")
    ids = upload_documents(_TEST_PROJECT, [a])
    assert_equal([_get_hash(a)], ids)

    d = get_document(_TEST_PROJECT, ids[0])
    assert_equal(d['title'], a['title'])
    # todo check date type
