from nose.tools import assert_equal

from tests.tools import QueryTestCase


class TestQuery(QueryTestCase):
    documents = [
        {'y': 3, 'cat': 'a', 'subcat': 'x', 'i': 1, 'date': '2018-01-01', 'text': "This is a text"},
        {'y': 2, 'cat': 'a', 'subcat': 'x', 'i': 2, 'date': '2018-02-01', 'text': "And another text"},
        {'y': 1, 'cat': 'a', 'subcat': 'y', 'i': 11, 'date': '2020-01-01', 'text': "Test document with words"},
        {'y': 2, 'cat': 'b', 'subcat': 'y', 'i': 31, 'date': '2018-01-01', 'text': "This is a document"},
    ]
    columns = {'cat': 'keyword', 'subcat': 'keyword'}

    def test_query(self):
        """Can we run a simple query?"""
        self.query(user=None, check=401, check_error="Querying requries authorization")
        assert_equal(self.q("text"), {1, 2})
        assert_equal(self.q("te*"), {1, 2, 11})

    def test_filters(self):
        """Do GET filters work as expected"""
        assert_equal(self.q(cat="a"), {1, 2, 11})
        assert_equal(self.q(date="2018-02-01"), {2})
        assert_equal(self.q(date__gt="2018-02-01"), {11})
        assert_equal(self.q(date__gte="2018-02-01"), {2, 11})
        assert_equal(self.q(date__gte="2018-02-01", date__lt="2020-01-01"), {2})
        assert_equal(self.q(cat="a", date__gt="2018-01-01"), {2, 11})

    def test_sorting(self):
        """Does sorting work?"""
        assert_equal(self.q(sort="_id", result=list), [1, 2, 11, 31])
        assert_equal(self.q(sort="_id:desc", result=list), [31, 11, 2, 1])
        assert_equal(self.q(sort="y,_id", result=list), [11, 2, 31, 1])

    def test_get_multiple_queries(self):
        """Can we use more than one query?"""
        assert_equal(self.q("this", "test"), {1, 11, 31})

    def test_query_post(self):
        """Does the POST end point work with queries and filters"""
        assert_equal(self.qp(), {1, 2, 11, 31})
        assert_equal(self.qp("te*", filters={'date': {'value': '2018-02-01'}}), {2})
        assert_equal(self.qp("te*", filters={'date': {'range': {'lt': '2018-02-01'}}}), {1})
        assert_equal(self.qp("te*", filters={'date': {'range': {'lte': '2018-02-01'}}}), {1, 2})
        assert_equal(self.qp(filters={'date': {'range': {'lt': '2020-01-01'}}}), {1, 2, 31})

    def test_fields(self):
        """Can we request specific fields?"""
        all_fields = {"_id", "date", "text", "title", "cat", "subcat", "i", "y"}
        assert_equal(set(self.query()['results'][0].keys()), all_fields)
        assert_equal(set(self.query(fields="cat")['results'][0].keys()), {"_id", "cat"})
        assert_equal(set(self.query(fields="date,title")['results'][0].keys()), {"_id", "date", "title"})

        assert_equal(set(self.query_post()['results'][0].keys()), all_fields)
        assert_equal(set(self.query_post(fields=["cat"])['results'][0].keys()), {"_id", "cat"})
        assert_equal(set(self.query_post(fields=["date", "title"])['results'][0].keys()), {"_id", "date", "title"})

    def test_aggregate_post(self):
        """Can we aggregate on one or more fields?"""
        def q(axes):
            for row in self.query_post(endpoint='aggregate', axes=axes):
                key = tuple(row[x['field']] for x in axes)
                yield (key, row['n'])

        self.query_post(endpoint='aggregate', check=400, check_error="Aggregate requires axes")
        assert_equal(dict(q(axes=[{'field': 'cat'}])), {("a",): 3, ("b",): 1})
        assert_equal(dict(q(axes=[{'field': 'cat'}, {'field': 'date', 'interval': 'year'}])),
                     {("a", "2018-01-01"): 2, ("a", "2020-01-01"): 1, ("b", "2018-01-01"): 1})

