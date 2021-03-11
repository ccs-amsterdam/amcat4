import random
import string

from nose.tools import assert_equal

from amcat4.auth import Role
from tests.tools import with_index, upload, ApiTestCase, delete_index


class TestIndex(ApiTestCase):

    def test_index_auth(self):
        """test_index_auth: Check that proper authentication is in place"""
        self.get('/index/', user=None, check=401, check_error="Getting index list should require authorization")
        self.post('/index/', user=None, check=401, check_error="Creating a index should require authorization")
        self.post('/index/', user=self.user, check=401,
                  check_error="Creating an index should require admin or creator role")

        self.get('/index/doesnotexist', check=404, check_error="Unknown index should return 404")
        self.put('/index/doesnotexist', check=404, check_error="Unknown index should return 404")

        url = '/index/' + self.index.name
        self.get(url, user=None, check=401, check_error="Viewing an index requires authorization")
        self.get(url, user=self.user, check=401, check_error="Viewing an index requires at least metareader role")
        self.put(url, user=None, check=401, check_error="Modifying an index requires authorization")
        self.put(url, user=self.user, check=401, check_error="Modifying an index requires writer role on the index")

        self.index.guest_role = Role.METAREADER
        self.index.save()
        self.get(url, user=self.user)
        self.put(url, user=self.user, check=401, check_error="Modifying an index requires writer role on the index")
        self.put(url, user=self.admin, json={})
        self.index.set_role(self.user, Role.WRITER)
        self.put(url, user=self.admin, json={})
        self.put(url, user=self.user, json={'guest_role': 'ADMIN'},
                 check=401, check_error="Setting guest role to admin requires admin role on the index")

    def test_create_list_index(self):
        def get_index(user):
            indices = {i['name']: i['role'] for i in self.get('/index/', user=user).json}
            return indices.get(_TEST_INDEX)

        _TEST_INDEX = 'amcat4_test__' + ''.join(random.choices(string.ascii_lowercase, k=32))
        assert_equal(get_index(user=self.admin), None)
        try:
            self.post('/index/', json=dict(name=_TEST_INDEX, guest_role='METAREADER'), user=self.admin)
            assert_equal(get_index(user=self.admin), 'ADMIN')
            assert_equal(get_index(user=self.user), 'METAREADER')
            self.delete(f'/index/{_TEST_INDEX}', user=self.admin)
        finally:
            delete_index(_TEST_INDEX)

    def test_set_guest_role(self):
        url = '/index/' + self.index_name
        self.index.guest_role = None
        self.index.save()
        assert_equal(self.get(url, user=self.admin).json['guest_role'], None)
        self.put(url, user=self.admin, json={'guest_role': 'READER'})
        assert_equal(self.get(url, user=self.admin).json['guest_role'], 'READER')
        self.put(url, user=self.admin, json={'guest_role': None})
        assert_equal(self.get(url, user=self.admin).json['guest_role'], None)

    def test_fields(self):
        """test_fields: Can we set and retrieve field mappings and values?"""
        url = 'index/{}/fields'.format(self.index_name)
        assert_equal(self.get(url).json, dict(date="date", text="text", title="text", url="keyword"))
        upload([{'x': x} for x in ("a", "a", "b")], index_name=self.index_name, columns={"x": "keyword"})
        assert_equal(self.get(url).json, dict(date="date", text="text", title="text", url="keyword", x="keyword"))
        url = 'index/{}/fields/x/values'.format(self.index_name)
        assert_equal(self.get(url).json, ["a", "b"])
