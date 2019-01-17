import base64
import random
import string

from nose.tools import assert_equal, assert_in, assert_not_in

from amcat4 import elastic
from amcat4.__main__ import app
from amcat4.auth import verify_token, create_user, ROLE_ADMIN, User
from amcat4.elastic import _get_hash

C = None
_TEST_ADMIN: User = None
_TEST_USER: User = None


def setup_module():
    global C, _TEST_ADMIN, _TEST_USER
    C = app.test_client()
    C.testing = True
    rnd_suffix = ''.join(random.choices(string.ascii_lowercase, k=32))
    _TEST_ADMIN = create_user("__test__admin__"+rnd_suffix, "password", roles=ROLE_ADMIN, check_email=False)
    _TEST_USER = create_user("__test__user__"+rnd_suffix, "password", check_email=False)


def teardown_module():
    _TEST_ADMIN and _TEST_ADMIN.delete(ignore_missing=True)
    _TEST_USER and _TEST_USER.delete(ignore_missing=True)


def _request(url, method='get', user=None, password="password", check={200, 201}, **kwargs):
    if user is None:
        user = _TEST_USER
    request_method = getattr(C, method)
    cred = ":".join([user.email, password])
    auth = base64.b64encode(cred.encode("ascii")).decode('ascii')
    result = request_method(url, headers={"Authorization": "Basic {}".format(auth)}, **kwargs)
    if check and result.status_code not in check:
        assert_in(result.status_code, check, result.get_data(as_text=True))
    return result


def _get(url, **kwargs):
    return _request(url, method='get', **kwargs)


def _post(url, **kwargs):
    return _request(url, method='post', **kwargs)


def test_get_token():
    assert_equal(C.get('/auth/token/').status_code, 401, "Getting project list should require authorization")
    r = _get('/auth/token/')
    token = r.json['token']
    assert_equal(verify_token(token), _TEST_USER)


def test_project():
    _TEST_PROJECT = '__test__' + ''.join(random.choices(string.ascii_lowercase, k=32))
    assert_not_in(dict(name=_TEST_PROJECT), _get('/projects/').json)

    assert_equal(C.get('/projects/').status_code, 401, "Getting project list should require authorization")
    assert_equal(C.post('/projects/').status_code, 401, "Creating a project should require authorization")
    assert_equal(_post('/projects/', json=dict(name=_TEST_PROJECT), user=_TEST_USER, check=False).status_code,
                 401, "Creating a project should require admin or creator role")

    _post('/projects/', json=dict(name=_TEST_PROJECT), user=_TEST_ADMIN)
    assert_in(dict(name=_TEST_PROJECT), _get('/projects/').json)


def test_documents():
    _TEST_PROJECT = '__test__' + ''.join(random.choices(string.ascii_lowercase, k=32))
    elastic.create_project(_TEST_PROJECT)
    try:
        url = 'projects/{}/documents'.format(_TEST_PROJECT)
        assert_equal(C.get(url).status_code, 401, "Reading documents requires authorization")
        assert_equal(C.post(url).status_code, 401, "Reading documents requires authorization")

        def query_ids(q=None):
            _url = "{url}?q={q}".format(**locals()) if q else url
            return {d['_id'] for d in _get(_url).json['results']}

        assert_equal(query_ids(), set())
        docs = [{"title": "t", "text": t, "date": "2018-01-01"} for t in ["a test", "another text"]]
        id0, id1 = [_get_hash(d) for d in docs]
        _post(url, json=docs)
        elastic.flush()
        assert_equal(query_ids(), {id0, id1})
        assert_equal(query_ids("test"), {id0})
        assert_equal(query_ids("text"), {id1})
        assert_equal(query_ids("te*"), {id0, id1})
        assert_equal(query_ids("foo"), set())
    finally:
        elastic.delete_project(_TEST_PROJECT, ignore_missing=True)


