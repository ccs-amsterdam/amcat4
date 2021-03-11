import base64
import random
import string
import urllib
from functools import wraps
from typing import Optional, Mapping, Iterable

from nose.tools import assert_equal, assert_false

from amcat4.auth import create_user, User, Role

from amcat4 import elastic, index
from amcat4.index import Index

_TEST_INDEX = 'amcat4_testindex__'


def create_index(name=_TEST_INDEX) -> str:
    elastic._delete_index(name, ignore_missing=True)
    elastic._create_index(name)
    return name


def delete_index(name=_TEST_INDEX):
    try:
        Index.get(name=name).delete_index()
    except Index.DoesNotExist:
        elastic._delete_index(name, ignore_missing=True)


def with_index(f):
    """
    Setup a clean elasticsearch database
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        index = create_index()
        try:
            return f(*args, index_name=index, **kwargs)
        finally:
            delete_index()
    return wrapper


def upload(docs, index_name: str = _TEST_INDEX, **kwargs):
    """
    Upload these docs to the index, giving them an incremental id, and flush
    """
    for i, doc in enumerate(docs):
        defaults = {'title': "title", 'date': "2018-01-01", 'text': "text", '_id': str(i)}
        for k, v in defaults.items():
            if k not in doc:
                doc[k] = v
    ids = elastic.upload_documents(index_name, docs, **kwargs)
    elastic.refresh(index_name)
    return ids


def assert_set_contains(superset: Iterable, subset: Iterable):
    """Test whether all elements of subset are contained in superset"""
    remainder = set(subset) - set(superset)
    assert_false(remainder, "Elements in second value not contained in first: {}".format(remainder))


class ApiTestCase:
    C = None
    user: User = None
    admin: User = None
    writer: User = None
    documents: Iterable[Mapping] = None
    columns: Mapping = None
    index: Index = None

    @classmethod
    def setup_class(cls: 'ApiTestCase'):
        from amcat4.api import app
        cls.C = app.test_client()
        cls.C.testing = True
        rnd_suffix = ''.join(random.choices(string.ascii_lowercase, k=32))
        cls.user = create_user("__test__user__"+rnd_suffix, "password")
        cls.admin = create_user("__test__admin__"+rnd_suffix, "password", global_role=Role.ADMIN)
        cls.writer = create_user("__test__writer__"+rnd_suffix, "password", global_role=Role.WRITER)
        cls.index_name = create_index()
        cls.index = index.create_index(cls.index_name, create_in_elastic=False, admin=cls.admin)
        if cls.documents:
            upload(cls.documents, cls.index.name, columns=getattr(cls, 'columns', None))

    @classmethod
    def teardown_class(cls):
        if cls.index_name:
            delete_index(cls.index_name)
        if cls.index:
            cls.index.delete_index(delete_from_elastic=False)


    def request(self, url, method='get', user='test_user', password="password",
                check=None, check_error=None, **kwargs):
        if user == 'test_user':
            user = self.user
        if user is not None:
            cred = ":".join([user.email, password])
            auth = base64.b64encode(cred.encode("ascii")).decode('ascii')
            kwargs['headers'] = {"Authorization": "Basic {}".format(auth)}
        request_method = getattr(self.C, method)
        result = request_method(url, **kwargs)
        if check and result.status_code != check:
            msg = result.get_data(as_text=True)
            if check_error:
                msg = "{check_error} [{msg}]".format(**locals())
            assert_equal(result.status_code, check, msg)
        return result

    def get(self, url, check: Optional[int] = 200, **kwargs):
        return self.request(url, method='get', check=check, **kwargs)

    def post(self, url, check: Optional[int] = 201, **kwargs):
        return self.request(url, method='post', check=check, **kwargs)

    def delete(self, url, check: Optional[int] = 204, **kwargs):
        return self.request(url, method='delete', check=check, **kwargs)

    def put(self, url, check: Optional[int] = 200, **kwargs):
        return self.request(url, method='put', check=check, **kwargs)


class QueryTestCase(ApiTestCase):
    def query(self, *queries, check=200, check_error=None, user='test_user', **options):
        url = 'index/{}/query'.format(self.index_name)
        if options or queries:
            options = list(options.items()) if options else []
            options += [("q", query) for query in queries]
            query = urllib.parse.urlencode(options)
            url = "{url}?{query}".format(**locals())
        return self.get(url, user=user, check=check, check_error=check_error).json

    def query_post(self, *queries, endpoint='query', check=200, check_error=None,  **json):
        url = 'index/{self.index_name}/{endpoint}'.format(**locals())
        if queries:
            json['queries'] = queries
        return self.post(url, check=check, json=json, check_error=check_error).json

    def q(self, *queries, result=set, **args):
        return result(int(d['i']) for d in self.query(*queries, **args)['results'])

    def qp(self, *queries, **args):
        return {int(d['i']) for d in self.query_post(*queries, **args)['results']}
