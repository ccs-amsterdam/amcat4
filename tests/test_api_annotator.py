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
        unit = self.get(f'/codingjob/{id}/unit?user=piet', user=None, check=200).json
        assert_equal(unit['unit']['text'], "zin 1")

        # Add a coding
        self.post(f"/codingjob/{id}/unit/{unit['id']}/annotation?user=piet", user=None, check=204, json=dict(foo='bar'))

        # Get the next unit
        unit = self.get(f'/codingjob/{id}/unit?user=piet', user=None, check=200).json
        assert_equal(unit['unit']['text'], "zin 2")

        # Get a unit as a second coder. This should be unit 2 again since unit 1 has been coded once already
        unit = self.get(f'/codingjob/{id}/unit?user=jan', user=None, check=200).json
        assert_equal(unit['unit']['text'], "zin 2")

        # Add a coding for unit 2, and check that getting next unit gives 404
        self.post(f"/codingjob/{id}/unit/{unit['id']}/annotation?user=piet", user=None, check=204, json=dict(bar='foo'))
        self.get(f'/codingjob/{id}/unit?user=piet', user=None, check=404)

        # Is the coding registered?
        result = self.get(f'/codingjob/{id}', user=self.admin, check=200).json
        assert_equal(result['units'][0]['annotations'], dict(piet=dict(foo='bar')))
        assert_equal(result['units'][1]['annotations'], dict(piet=dict(bar='foo')))
