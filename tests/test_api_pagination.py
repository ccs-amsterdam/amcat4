import urllib
from nose.tools import assert_equal, assert_is_not_none

from tests.tools import QueryTestCase


class TestQuery(QueryTestCase):
    documents = [{'i': i} for i in range(66)]

    def test_pagination(self):
        """Does basic pagination work?"""
        r = self.query(sort="i", per_page=20)
        assert_equal(r['meta']['per_page'], 20)
        assert_equal(r['meta']['page'], 0)
        assert_equal(r['meta']['page_count'], 4)
        assert_equal({h['i'] for h in r['results']}, set(range(20)))
        r = self.query(sort="i", per_page=20, page=3)
        assert_equal(r['meta']['per_page'], 20)
        assert_equal(r['meta']['page'], 3)
        assert_equal(r['meta']['page_count'], 4)
        assert_equal({h['i'] for h in r['results']}, {60, 61, 62, 63, 64, 65})

    def test_scrolling(self):
        """Can we scroll through a query?"""
        r = self.query(per_page=30, sort="i", scroll="5m")
        scroll_id = r['meta']['scroll_id']
        assert_is_not_none(scroll_id)
        assert_equal({h['i'] for h in r['results']}, set(range(30)))
        r = self.query(scroll_id=scroll_id)
        assert_equal({h['i'] for h in r['results']}, set(range(30, 60)))
        assert_equal(r['meta']['scroll_id'], scroll_id)
        r = self.query(scroll_id=scroll_id)
        assert_equal({h['i'] for h in r['results']}, {60, 61, 62, 63, 64, 65})
        assert_equal(r['meta']['scroll_id'], scroll_id)
        self.query(scroll_id=scroll_id, check=404, check_error="It should throw 404 to indicate no more results")
