import base64
import random
import string

from nose.tools import assert_equal, assert_in, assert_not_in

from amcat4.__main__ import app
from amcat4.auth import verify_token, create_user, delete_user, ROLE_ADMIN

C = None
_TEST_ADMIN = '__test__admin__'+ ''.join(random.choices(string.ascii_lowercase, k=32))
_TEST_USER = '__test__user__'+ ''.join(random.choices(string.ascii_lowercase, k=32))


def setup_module():
    global C
    C = app.test_client()
    C.testing = True
    create_user(_TEST_ADMIN, "password", roles=ROLE_ADMIN, check_email=False)
    create_user(_TEST_USER, "password", check_email=False)



def teardown_module():
    delete_user(_TEST_ADMIN, ignore_missing=True)
    delete_user(_TEST_USER, ignore_missing=True)


def _request(url, method='get', user=_TEST_USER, password="password", **kwargs):
    request_method = getattr(C, method)
    cred = ":".join([user, password])
    auth = base64.b64encode(cred.encode("ascii")).decode('ascii')
    result = request_method(url, headers={"Authorization": "Basic {}".format(auth)}, **kwargs)
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
    assert_equal(verify_token(token), _TEST_USER)


def test_project():
    assert_equal(C.get('/projects/').status_code, 401, "Getting project list should require authorization")
    assert_equal(C.post('/projects/').status_code, 401, "Creating a project should require authorization")

    _TEST_PROJECT = '__test__' + ''.join(random.choices(string.ascii_lowercase, k=32))
    assert_not_in(dict(name=_TEST_PROJECT), _get('/projects/').json)
    #_t('/projects/', json=dict(name="test123"))
    _post('/projects/', json=dict(name=_TEST_PROJECT))
    assert_in(dict(name=_TEST_PROJECT), _get('/projects/').json)
