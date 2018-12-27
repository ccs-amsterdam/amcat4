import random
import string

from amcat4api.elastic import create_project, list_projects, delete_project


def test_create_delete_list_project():
    name = '__test__' + ''.join(random.choices(string.ascii_lowercase, k=32))
    try:
        assert name not in list_projects()
        create_project(name)
        assert name in list_projects()
        delete_project(name)
        assert name not in list_projects()
    finally:
        delete_project(name, ignore_missing=True)

