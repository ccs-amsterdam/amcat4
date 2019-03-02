import random
import string

from nose.tools import assert_equal

from tests.tools import with_index, upload, ApiTestCase


class TestIndex(ApiTestCase):

    def test_index(self):
        def indices():
            return {i['name'] for i in self.get('/index/', user=self.admin).json}

        _TEST_INDEX = 'amcat4_test__' + ''.join(random.choices(string.ascii_lowercase, k=32))
        assert_equal(indices(), set())

        self.get('/index/', user=None, check=401, check_error="Getting index list should require authorization")
        self.post('/index/', user=None, check=401, check_error="Creating a indexshould require authorization")
        self.post('/index/', json=dict(name=_TEST_INDEX), user=self.user,
                  check=401, check_error="Creating an index should require admin or creator role")

        self.post('/index/', json=dict(name=_TEST_INDEX), user=self.admin)
        assert_equal(indices(), {_TEST_INDEX})

    @with_index
    def test_fields(self, index_name):
        """Can we set and retrieve field mappings and values?"""
        url = 'index/{}/fields'.format(index_name)
        assert_equal(self.get(url).json, dict(date="date", text="text", title="text", url="keyword"))
        upload([{'x': x} for x in ("a", "a", "b")], columns={"x": "keyword"})
        assert_equal(self.get(url).json, dict(date="date", text="text", title="text", url="keyword", x="keyword"))
        url = 'index/{}/fields/x/values'.format(index_name)
        assert_equal(self.get(url).json, ["a", "b"])


