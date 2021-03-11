from nose.tools import assert_equal

from amcat4 import elastic
from amcat4.api.index import _index
from amcat4.auth import User, Role
from tests.tools import QueryTestCase, with_index, upload

ANNOTATIONS = [{'x': 1}, {'x': 2, 'y': 1}]
_TEST_DOCUMENTS = [
    {'date': '2018-01-01', 'text': 'this is a text', 'annotations': ANNOTATIONS},
]


class TestAPIAnnotations(QueryTestCase):
    documents = _TEST_DOCUMENTS

    def test_update(self):
        """Can we update a field on a document?"""
        _id, = upload(_TEST_DOCUMENTS, self.index_name)
        a = elastic.get_document(self.index_name, _id, _source=['annotations'])['annotations']
        assert_equal(a, ANNOTATIONS)
        elastic.update_document(self.index_name, _id, {'annotations': {'x': 3}})
        a = elastic.get_document(self.index_name, _id, _source=['annotations'])['annotations']
        assert_equal(a, {'x': 3})

    def test_api_annotations(self):
        """Can we update a field using the API?"""
        assert_equal(self.query(fields="annotations")['results'][0]['annotations'], ANNOTATIONS)
        url = f"/index/{self.index_name}/documents/0?fields=annotations"
        assert_equal(self.get(url, user=self.admin).json['annotations'], ANNOTATIONS)
        url = f"/index/{self.index_name}/documents/0"
        self.put(url, json={"annotations": {'x': 3}}, user=self.admin)
        assert_equal(self.get(url, user=self.admin).json['annotations'], {'x': 3})

    def test_update_auth(self):
        """Do you need write permission to update?"""
        url = f"/index/{self.index_name}/documents/0"
        self.put(url, json={"x": 1}, user=self.user,
                 check=401, check_error="User without rights on index can't update a document")
        #TODO: do this using API
        user = User.get(User.email == self.user.email)
        _index(self.index_name).set_role(user, Role.WRITER)
        self.put(url, json={"x": 1}, user=self.user)







