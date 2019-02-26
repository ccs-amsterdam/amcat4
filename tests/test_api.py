import base64
import functools
import random
import string
import urllib.parse
from collections import namedtuple

from nose.tools import assert_equal, assert_in, assert_not_in, assert_is_not_none, assert_raises

from amcat4 import elastic
from amcat4.__main__ import app
from amcat4.auth import verify_token, create_user, User, Role
from amcat4.elastic import _delete_index

from tests.tools import with_index, upload

C = None
_TEST_ADMIN: User = None
_TEST_USER: User = None
_TEST_WRITER: User = None
NO_USER = object()  # sorry!

def setup_module():
    global C, _TEST_ADMIN, _TEST_USER, _TEST_WRITER
    C = app.test_client()
    C.testing = True
    rnd_suffix = ''.join(random.choices(string.ascii_lowercase, k=32))
    _TEST_ADMIN = create_user("__test__admin__"+rnd_suffix, "password", global_role=Role.ADMIN)
    _TEST_USER = create_user("__test__user__"+rnd_suffix, "password")
    _TEST_WRITER = create_user("__test__writer__"+rnd_suffix, "password", global_role=Role.WRITER)


def teardown_module():
    _TEST_ADMIN and _TEST_ADMIN.delete_instance()
    _TEST_USER and _TEST_USER.delete_instance()
    _TEST_WRITER and _TEST_USER.delete_instance()


def _request(url, method='get', user=None, password="password", check=None, **kwargs):
    if user is None:
        user = _TEST_USER
    if user == NO_USER:
        user = None  # I said sorry, ok?
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


def _delete(url, check=204, **kwargs):
    return _request(url, method='delete', check=check, **kwargs)


def test_get_token():
    assert_equal(C.get('/auth/token/').status_code, 401, "Getting index list should require authorization")
    r = _get('/auth/token/')
    token = r.json['token']
    assert_equal(verify_token(token), _TEST_USER)
    assert_equal(C.get('/index/').status_code, 401)
    assert_equal(C.get('/index/', headers={"Authorization": "Bearer {}".format(token)}).status_code, 200)


def test_index():
    def indices():
        return {i['name'] for i in _get('/index/', user=_TEST_ADMIN).json}

    _TEST_INDEX = 'amcat4_test__' + ''.join(random.choices(string.ascii_lowercase, k=32))
    assert_equal(indices(), set())

    assert_equal(C.get('/index/').status_code, 401, "Getting index list should require authorization")
    assert_equal(C.post('/index/').status_code, 401, "Creating a indexshould require authorization")
    assert_equal(_post('/index/', json=dict(name=_TEST_INDEX), user=_TEST_USER, check=False).status_code,
                 401, "Creating an index should require admin or creator role")

    _post('/index/', json=dict(name=_TEST_INDEX), user=_TEST_ADMIN)
    assert_equal(indices(), {_TEST_INDEX})


def test_index_roles():
    """Does a user get the correct role with an index?"""


def _query(index, check=200, **options):
    url = 'index/{}/query'.format(index)
    if options:
        query = urllib.parse.urlencode(options)
        url = "{url}?{query}".format(**locals())
    return _get(url, check=check).json


def _query_post(index, endpoint='query', check=200, **json):
    url = 'index/{index}/{endpoint}'.format(**locals())
    return _post(url, check=check, json=json).json


@with_index
def test_upload(index):
    docs = [{"title": "title", "text": "text", "date": "2018-01-01"},
            {"title": "titel", "text": "more text", "custom": "x"}]
    url = 'index/{}/documents'.format(index)
    res = _post(url, json=docs, check=None)
    assert_equal(res.status_code, 500, "Check for missing fields")
    docs[1]['date'] = '2010-12-31'
    _post(url, json=docs)
    elastic.refresh()
    res = _query(index)['results']
    assert_equal(len(res), 2)
    assert_equal({d['title'] for d in res}, {"title", "titel"})
    assert_equal({d.get('custom') for d in res}, {"x", None})


@with_index
def test_get_document(index):
    _get("/index/{}/documents/{}".format(index, "testdoc"), check=404)
    upload([{"title": "de titel", "_id": "testdoc" }])
    assert_equal(_get("/index/{}/documents/{}".format(index, "testdoc")).json['title'], 'de titel')


@with_index
def test_documents(index):
    def q(**q):
        return {int(d['_id']) for d in _query(index, **q)['results']}
    url = 'index/{}/query'.format(index)
    assert_equal(C.get(url).status_code, 401, "Reading documents requires authorization")
    assert_equal(C.post(url).status_code, 401, "Reading documents requires authorization")

    assert_equal(q(), set())
    upload([{"title": "t", "text": t, "date": "2018-01-01"} for t in ["a test", "another text"]])
    assert_equal(q(), {0, 1})
    assert_equal(q(q="test"), {0})
    assert_equal(q(q="text"), {1})
    assert_equal(q(q="te*"), {0, 1})
    assert_equal(q(q="foo"), set())


@with_index
def test_fields(index):
    upload([{"cat": "a"}])
    assert_equal(set(_query(index)['results'][0].keys()), {"_id", "date", "cat", "text", "title", "_id"})
    assert_equal(set(_query(index, fields="cat")['results'][0].keys()), {"_id", "cat"})
    assert_equal(set(_query(index, fields="date,title")['results'][0].keys()), {"_id", "date", "title"})

    assert_equal(set(_query_post(index)['results'][0].keys()), {"_id", "date", "cat", "text", "title", "_id"})
    assert_equal(set(_query_post(index, fields=["cat"])['results'][0].keys()), {"_id", "cat"})
    assert_equal(set(_query_post(index, fields=["date", "title"])['results'][0].keys()), {"_id", "date", "title"})


@with_index
def test_sorting(index):
    def q(**q):
        return [int(d['_id']) for d in _query(index, **q)['results']]
    upload([{'f': x} for x in [3, 2, 1, 2, 3]])
    assert_equal(q(sort="_id"), [0, 1, 2, 3, 4])
    assert_equal(q(sort="_id:desc"), [4, 3, 2, 1, 0])
    assert_equal(q(sort="f,_id"), [2, 1, 3, 0, 4])


@with_index
def test_pagination(index):
    upload([{'i': i} for i in range(66)])
    r = _query(index, sort="i", per_page=20)
    assert_equal(r['meta']['per_page'], 20)
    assert_equal(r['meta']['page'], 0)
    assert_equal(r['meta']['page_count'], 4)
    assert_equal({h['i'] for h in r['results']}, set(range(20)))
    r = _query(index, sort="i", per_page=20, page=3)
    assert_equal(r['meta']['per_page'], 20)
    assert_equal(r['meta']['page'], 3)
    assert_equal(r['meta']['page_count'], 4)
    assert_equal({h['i'] for h in r['results']}, {60, 61, 62, 63, 64, 65})


@with_index
def test_scrolling(index):
    upload([{'i': i} for i in range(10)])
    r = _query(index, per_page=4, sort="i", scroll="5m")
    scroll_id = r['meta']['scroll_id']
    assert_is_not_none(scroll_id)
    assert_equal({h['i'] for h in r['results']}, {0, 1, 2, 3})
    r = _query(index, scroll_id=scroll_id)
    assert_equal({h['i'] for h in r['results']}, {4, 5, 6, 7})
    assert_equal(r['meta']['scroll_id'], scroll_id)
    r = _query(index, scroll_id=scroll_id)
    assert_equal({h['i'] for h in r['results']}, {8, 9})
    assert_equal(r['meta']['scroll_id'], scroll_id)
    _query(index, scroll_id=scroll_id, check=404)


@with_index
def test_mapping(index):
    url = 'index/{}/fields'.format(index)
    assert_equal(_get(url).json, dict(date="date", text="text", title="text", url="keyword"))
    upload([{'x': x} for x in ("a", "a", "b")], columns={"x": "keyword"})
    assert_equal(_get(url).json, dict(date="date", text="text", title="text", url="keyword", x="keyword"))
    url = 'index/{}/fields/x/values'.format(index)
    assert_equal(_get(url).json, ["a", "b"])


@with_index
def test_filters(index):
    def q(**q):
        return {int(d['_id']) for d in _query(index, **q)['results']}
    upload([{'x': "a", 'date': '2012-01-01'},
            {'x': "a", 'date': '2012-02-01'},
            {'x': "b", 'date': '2012-03-01'},])
    assert_equal(q(x="a"), {0, 1})
    assert_equal(q(date="2012-01-01"), {0})
    assert_equal(q(date__gt="2012-01-01"), {1, 2})
    assert_equal(q(date__gt="2012-01-01", date__lte="2012-02-01"), {1})
    assert_equal(q(x="a", date__gt="2012-01-01"), {1})


@with_index
def test_query_post(index):
    q = functools.partial(_query_post, index=index, endpoint='query')
    upload([{'x': "a", 'date': '2012-01-01', 'i': 1},
            {'x': "a", 'date': '2012-02-01', 'i': 2},
            {'x': "b", 'date': '2012-03-01', 'i': 3},])
    assert_equal({h['i'] for h in q()['results']}, {1, 2, 3})
    assert_equal({h['i'] for h in q(q="b")['results']}, {3})
    assert_equal({h['i'] for h in q(q="a", filters={'date': {'value': '2012-02-01'}})['results']}, {2})
    assert_equal({h['i'] for h in q(q="a", filters={'date': {'range': {'lt':'2012-02-01'}}})['results']}, {1})

    # test pagination and scrolling via post
    res = q(per_page=2, sort="i:desc")
    assert_not_in('scroll_id', res['meta'])
    assert_equal(res['meta']['page'], 0)
    assert_equal([x['i'] for x in res['results']], [3, 2])
    res = q(per_page=2, sort="i:desc", page=1)
    assert_equal([x['i'] for x in res['results']], [1])

    res = q(scroll=True, per_page=2, sort="i:desc")
    assert_in('scroll_id', res['meta'])
    assert_not_in('page', res['meta'])
    assert_equal([x['i'] for x in res['results']], [3, 2])

    scroll_id = res['meta']['scroll_id']
    res = q(scroll_id=scroll_id)
    assert_equal([x['i'] for x in res['results']], [1])


@with_index
def test_aggregate_post(index):
    def q(axes):
        for row in _query_post(index, 'aggregate', axes=axes):
            key = tuple(row[x['field']] for x in axes)
            yield (key, row['n'])

    upload([{'cat': 'a', 'subcat': 'x', 'i': 1, 'date': '2018-01-01'},
            {'cat': 'a', 'subcat': 'x', 'i': 2, 'date': '2018-02-01'},
            {'cat': 'a', 'subcat': 'y', 'i': 11, 'date': '2020-01-01'},
            {'cat': 'b', 'subcat': 'y', 'i': 31, 'date': '2018-01-01'},
            ], columns={'cat': 'keyword', 'subcat': 'keyword'})

    _query_post(index, 'aggregate', check=400)
    assert_equal(dict(q(axes=[{'field': 'cat'}])), {("a",): 3, ("b",): 1})
    assert_equal(dict(q(axes=[{'field': 'cat'}, {'field': 'date', 'interval': 'year'}])),
                 {("a", "2018-01-01"): 2,  ("a", "2020-01-01"): 1, ("b", "2018-01-01"): 1})


def _getuser(user, as_user = None, **args):
    if not isinstance(user, str):
        user = user.email
    return _get("/users/"+user, user=as_user, **args).json


def test_get_user():
    assert_equal(C.get('/users/unknown').status_code, 401, "Viewing user should require auth")
    _getuser("unknown user", as_user=NO_USER, check=401)
    _getuser(_TEST_USER, as_user=NO_USER, check=401)

    # user can only see its own info:
    assert_equal(_getuser(_TEST_USER, as_user=_TEST_USER), {"email": _TEST_USER.email, "global_role": None})
    _getuser(_TEST_ADMIN, as_user=_TEST_USER, check=401)
    # admin can see everyone
    assert_equal(_getuser(_TEST_ADMIN, as_user=_TEST_ADMIN), {"email": _TEST_ADMIN.email, "global_role": 'ADMIN'})
    assert_equal(_getuser(_TEST_USER, as_user=_TEST_ADMIN), {"email": _TEST_USER.email, "global_role": None})


def test_create_user():
    assert_equal(C.post('/users/').status_code, 401, "Creating user should require auth")
    _user = namedtuple("_user", "email pwd")
    u = _user(email='testuser@example.com', pwd='test')
    _post("/users/", user=_TEST_USER, check=401)  # creating user requires >=WRITER

    _getuser(u, as_user=_TEST_ADMIN, check=404)
    _post("/users/", user=_TEST_WRITER, json=dict(email=u.email, password=u.pwd))
    assert_equal(_getuser(u, as_user=u, password=u.pwd), {"email": u.email, "global_role": None})
    _post("/users/", user=_TEST_WRITER, json=dict(email=u.email, password=u.pwd), check=400)
    _delete("/users/"+u.email, user=_TEST_WRITER)

    _post("/users/", user=_TEST_WRITER, json=dict(email=u.email, password=u.pwd, global_role='ADMIN'),
          check=401)  # WRITER cannot create ADMIN
    _post("/users/", user=_TEST_ADMIN, json=dict(email=u.email, password=u.pwd, global_role='ADMIN'))
    assert_equal(_getuser(u, as_user=_TEST_WRITER), {"email": u.email, "global_role": 'ADMIN'})
    _delete("/users/" + u.email, user=_TEST_WRITER, check=401)  # WRITER cannot delete ADMIN
    _delete("/users/" + u.email, user=_TEST_ADMIN)




