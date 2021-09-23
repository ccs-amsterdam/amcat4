from nose.tools import assert_equal

from tests.tools import ApiTestCase


#TODO: clear up test codingjobs!
class TestAnnotator(ApiTestCase):
    def test_annotator(self):
        unit1 = dict(text="zin 1")
        unit2 = dict(text="zin 2")
        job = dict(title="Test", units=[unit1, unit2], codebook="CODEBOOK")
        # Create the codebook
        result = self.post('/codingjob', user=self.admin, check=201, json=job).json
        id = result['id']
        # Fetch the codingjob
        result = self.get(f'/codingjob/{id}', user=self.admin, check=200).json
        assert_equal(result['codebook'], "CODEBOOK")
        assert_equal(result['title'], "Test")

        # Ask for the codebook as coder
        codebook = self.get(f'/codingjob/{id}/codebook', user=None, check=200).json
        assert_equal(result['codebook'], "CODEBOOK")

        # Get the first unit
        unit = self.get(f'/codingjob/{id}/unit', user=None, check=200).json
        print("!!1", unit)
        assert_equal(unit['unit']['text'], "zin 1")

        # Add a coding
        self.post(f"/codingjob/{id}/unit/{unit['id']}/annotation", user=None, check=204, json=dict(foo='bar'))

        # Get the next unit
        unit = self.get(f'/codingjob/{id}/unit', user=None, check=200).json
        print("!!2", unit)
        assert_equal(unit['unit']['text'], "zin 2")

        # Is the coding registered?
        result = self.get(f'/codingjob/{id}', user=self.admin, check=200).json
        assert_equal(result['units'][0]['annotations'], dict(foo='bar'))
