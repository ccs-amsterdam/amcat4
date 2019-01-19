import random
import string
from functools import wraps

from amcat4 import elastic

_TEST_PROJECT = '__test__' + ''.join(random.choices(string.ascii_lowercase, k=32))


def with_project(f):
    """
    Setup a clean database
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        elastic.delete_project(_TEST_PROJECT, ignore_missing=True)
        elastic.create_project(_TEST_PROJECT)
        try:
            return f(_TEST_PROJECT, *args, **kwargs)
        finally:
            elastic.delete_project(_TEST_PROJECT, ignore_missing=True)
    return wrapper


def upload(docs, project=_TEST_PROJECT):
    """
    Upload these docs to the project, giving them an incremental id, and flush
    """
    for i, doc in enumerate(docs):
        defaults = {'title': "title", 'date': "2018-01-01", 'text': "text", '_id': str(i)}
        for k, v in defaults.items():
            if k not in doc:
                doc[k] = v
    ids = elastic.upload_documents(project, docs)
    elastic.refresh()
    return ids
