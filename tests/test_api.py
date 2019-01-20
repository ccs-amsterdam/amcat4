import base64
import random
import string
import urllib.parse

from nose.tools import assert_equal, assert_in, assert_not_in, assert_is_not_none

from amcat4 import elastic
from amcat4.__main__ import app
from amcat4.auth import verify_token, create_user, ROLE_ADMIN, User
from amcat4.elastic import _get_hash, delete_project

from tests.tools import with_project, upload

C = None
_TEST_ADMIN: User = None
_TEST_USER: User = None


def setup_module():
    global C, _TEST_ADMIN, _TEST_USER
    C = app.test_client()
    C.testing = True
    rnd_suffix = ''.join(random.choices(string.ascii_lowercase, k=32))
    _TEST_ADMIN = create_user("__test__admin__"+rnd_suffix, "password", roles=ROLE_ADMIN)
    _TEST_USER = create_user("__test__user__"+rnd_suffix, "password")


def teardown_module():
    _TEST_ADMIN and _TEST_ADMIN.delete(ignore_missing=True)
    _TEST_USER and _TEST_USER.delete(ignore_missing=True)


def _request(url, method='get', user=None, password="password", check=False, **kwargs):
    if user is None:
        user = _TEST_USER
    request_method = getattr(C, method)
    cred = ":".join([user.email, password])
    auth = base64.b64encode(cred.encode("ascii")).decode('ascii')
    result = request_method(url, headers={"Authorization": "Basic {}".format(auth)}, **kwargs)
    if check and result.status_code != check:
        assert_equal(result.status_code, check, result.get_data(as_text=True))
    return result


def _get(url, check=200, **kwargs):
    return _request(url, method='get', check=check, **kwargs)


def _post(url, check=201, **kwargs):
    return _request(url, method='post', check=check, **kwargs)


def test_get_token():
    assert_equal(C.get('/auth/token/').status_code, 401, "Getting project list should require authorization")
    r = _get('/auth/token/')
    token = r.json['token']
    assert_equal(verify_token(token), _TEST_USER)
    assert_equal(C.get('/projects/').status_code, 401)
    assert_equal(C.get('/projects/', headers={"Authorization": "Bearer {}".format(token)}).status_code, 200)


def test_project():
    _TEST_PROJECT = '__test__' + ''.join(random.choices(string.ascii_lowercase, k=32))
    delete_project(_TEST_PROJECT, ignore_missing=True)
    assert_not_in(dict(name=_TEST_PROJECT), _get('/projects/').json)

    assert_equal(C.get('/projects/').status_code, 401, "Getting project list should require authorization")
    assert_equal(C.post('/projects/').status_code, 401, "Creating a project should require authorization")
    assert_equal(_post('/projects/', json=dict(name=_TEST_PROJECT), user=_TEST_USER, check=False).status_code,
                 401, "Creating a project should require admin or creator role")

    _post('/projects/', json=dict(name=_TEST_PROJECT), user=_TEST_ADMIN)
    assert_in(dict(name=_TEST_PROJECT), _get('/projects/').json)


def _query(project, check=200, **options):
    url = 'projects/{}/documents'.format(project)
    if options:
        query = urllib.parse.urlencode(options)
        url = "{url}?{query}".format(**locals())
    return _get(url, check=check).json


@with_project
def test_upload(project):
    docs = [{"title": "title", "text": "text", "date": "2018-01-01"},
            {"title": "titel", "text": "more text", "custom": "x"}]
    url = 'projects/{}/documents'.format(project)
    res = _post(url, json=docs, check=None)
    assert_equal(res.status_code, 500, "Check for missing fields")
    docs[1]['date'] = '2010-12-31'
    _post(url, json=docs)
    elastic.refresh()
    res = _query(project)['results']
    assert_equal(len(res), 2)
    assert_equal({d['title'] for d in res}, {"title", "titel"})
    assert_equal({d.get('custom') for d in res}, {"x", None})




@with_project
def test_documents(project):
    def q(**q):
        return {int(d['_id']) for d in _query(project, **q)['results']}
    url = 'projects/{}/documents'.format(project)
    assert_equal(C.get(url).status_code, 401, "Reading documents requires authorization")
    assert_equal(C.post(url).status_code, 401, "Reading documents requires authorization")

    assert_equal(q(), set())
    upload([{"title": "t", "text": t, "date": "2018-01-01"} for t in ["a test", "another text"]])
    assert_equal(q(), {0, 1})
    assert_equal(q(q="test"), {0})
    assert_equal(q(q="text"), {1})
    assert_equal(q(q="te*"), {0, 1})
    assert_equal(q(q="foo"), set())


@with_project
def test_sorting(project):
    def q(**q):
        return [int(d['_id']) for d in _query(project, **q)['results']]
    upload([{'f': x} for x in [3, 2, 1, 2, 3]])
    assert_equal(q(sort="_id"), [0, 1, 2, 3, 4])
    assert_equal(q(sort="_id:desc"), [4, 3, 2, 1, 0])
    assert_equal(q(sort="f,_id"), [2, 1, 3, 0, 4])


@with_project
def test_pagination(project):
    upload([{'i': i} for i in range(66)])
    r = _query(project, sort="i", per_page=20)
    assert_equal(r['meta']['per_page'], 20)
    assert_equal(r['meta']['page'], 0)
    assert_equal(r['meta']['page_count'], 4)
    assert_equal({h['i'] for h in r['results']}, set(range(20)))
    r = _query(project, sort="i", per_page=20, page=3)
    assert_equal(r['meta']['per_page'], 20)
    assert_equal(r['meta']['page'], 3)
    assert_equal(r['meta']['page_count'], 4)
    assert_equal({h['i'] for h in r['results']}, {60, 61, 62, 63, 64, 65})


@with_project
def test_scrolling(project):
    upload([{'i': i} for i in range(10)])
    r = _query(project, per_page=4, sort="i", scroll="5m")
    scroll_id = r['meta']['scroll_id']
    assert_is_not_none(scroll_id)
    assert_equal({h['i'] for h in r['results']}, {0, 1, 2, 3})
    r = _query(project, scroll_id=scroll_id)
    assert_equal({h['i'] for h in r['results']}, {4, 5, 6, 7})
    assert_equal(r['meta']['scroll_id'], scroll_id)
    r = _query(project, scroll_id=scroll_id)
    assert_equal({h['i'] for h in r['results']}, {8, 9})
    assert_equal(r['meta']['scroll_id'], scroll_id)
    _query(project, scroll_id=scroll_id, check=404)


@with_project
def test_mapping(project):
    url = 'projects/{}/fields'.format(project)
    assert_equal(_get(url).json, dict(date="date", text="text", title="text", url="keyword"))
