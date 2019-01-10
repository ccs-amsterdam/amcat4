import base64
import random
import string

from nose.tools import assert_equal, assert_in, assert_not_in

from amcat4.__main__ import app
from amcat4.auth import verify_token

C = None


def setup_module():
    global C
    C = app.test_client()
    C.testing = True


def _request(url, method='get', **kwargs):
    request_method = getattr(C, method)
    auth = "Basic {}".format(base64.b64encode(b"admin:admin").decode('ascii'))
    result = request_method(url, headers={"Authorization": auth}, **kwargs)
    if result.status_code not in {200, 201}:
        assert_in(result.status_code, {200, 201}, result.get_data(as_text=True))
    return result


def _get(url, **kwargs):
    return _request(url, method='get', **kwargs)


def _post(url, **kwargs):
    return _request(url, method='post', **kwargs)


def test_get_token():
    assert_equal(C.get('/auth/token/').status_code, 401, "Getting project list should require authorization")
    r = _get('/auth/token/')
    token = r.json['token']
    assert_equal(verify_token(token), 'admin')


def test_project():
    assert_equal(C.get('/projects/').status_code, 401, "Getting project list should require authorization")
    assert_equal(C.post('/projects/').status_code, 401, "Creating a project should require authorization")

    _TEST_PROJECT = '__test__' + ''.join(random.choices(string.ascii_lowercase, k=32))
    assert_not_in(dict(name=_TEST_PROJECT), _get('/projects/').json)
    #_t('/projects/', json=dict(name="test123"))
    _post('/projects/', json=dict(name=_TEST_PROJECT))
    assert_in(dict(name=_TEST_PROJECT), _get('/projects/').json)
