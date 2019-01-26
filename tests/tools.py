import random
import string
from functools import wraps

from amcat4 import elastic

_TEST_INDEX = 'amcat4_testindex__'


def create_index(name=_TEST_INDEX):
    elastic.delete_index(name, ignore_missing=True)
    elastic.create_index(name)
    return name


def delete_index(name=_TEST_INDEX):
    elastic.delete_index(name, ignore_missing=True)


def with_index(f):
    """
    Setup a clean database
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        index = create_index()
        try:
            return f(index, *args, **kwargs)
        finally:
            delete_index()
    return wrapper


def upload(docs, index=_TEST_INDEX, **kwargs):
    """
    Upload these docs to the index, giving them an incremental id, and flush
    """
    for i, doc in enumerate(docs):
        defaults = {'title': "title", 'date': "2018-01-01", 'text': "text", '_id': str(i)}
        for k, v in defaults.items():
            if k not in doc:
                doc[k] = v
    ids = elastic.upload_documents(index, docs, **kwargs)
    elastic.refresh()
    return ids
