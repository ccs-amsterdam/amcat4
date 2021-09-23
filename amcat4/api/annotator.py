from typing import Optional

from flask import Blueprint, jsonify, request, abort, make_response
from werkzeug.exceptions import HTTPException

from amcat4.api.common import multi_auth, check_role
from amcat4.auth import Role
from amcat4.elastic import es

app_annotator = Blueprint('app_annotator', __name__)

"""
A coding job consists of the following information:
{"owner": <userid>,
 "title": <str>,
 "codebook": {...},
 "units": [{..}, ]
}
"""

@app_annotator.route("/codingjob", methods=['GET'])
@multi_auth.login_required
def list_jobs():
    """
    List coding jobs from this server. Returns a list of (all) codebooks
    """
    check_role(Role.ADMIN)


@app_annotator.route("/codingjob", methods=['POST'])
@multi_auth.login_required
def create_job():
    """
    Create a new codingjob. Body should be json adhering to structure above
    """
    check_role(Role.ADMIN)
    job = request.get_json(force=True)
    if {"title", "codebook", "units"} - set(job.keys()):
        return make_response({"error": "Codingjob should have title, codebook and units keys"}, 400)
    _check_annotations_index()
    job_id = _create_codingjob(job)
    return make_response(dict(id=job_id), 201)


@app_annotator.route("/codingjob/<id>", methods=['GET'])
@multi_auth.login_required
def get_job(id):
    """
    Return a single coding job definition
    """
    check_role(Role.ADMIN)
    _check_annotations_index()
    return _get_codingjob(id)


@app_annotator.route("/codingjob/<id>/codebook", methods=['GET'])
def get_codebook(id):
    job = _get_codingjob(id)
    return job['codebook']


@app_annotator.route("/codingjob/<id>/unit", methods=['GET'])
def get_next_unit(id):
    """
    Retrieve a single unit to be coded. Currently, the next uncoded unit
    """
    job = _get_codingjob(id)
    for i, unit in enumerate(job['units']):
        print(unit)
        if not unit.get('status') == "DONE":
            return {'id': i, 'unit': unit}
    abort(404)

@app_annotator.route("/codingjob/<job_id>/unit/<int:unit_id>/annotation", methods=['POST'])
def set_annotation(job_id, unit_id):
    """Set the annotations for a specific unit"""
    job = _get_codingjob(job_id)
    annotations = request.get_json(force=True)

    job["units"][unit_id]["annotations"] = annotations
    job["units"][unit_id]["status"] = "DONE"
    es.index(INDEX, id=job_id, body=job)
    return make_response('', 204)


INDEX = "amcat4_annotations"


def _check_annotations_index():
    if not es.indices.exists(INDEX):
        es.indices.create(INDEX)


def _codingjob_exists(id: str) -> bool:
    return es.exists(index=INDEX, id=id)


def _create_codingjob(job: dict) -> str:
    return es.index(INDEX, job)['_id']


def _get_codingjob(id: str) -> dict:
    return es.get(INDEX, id=id)['_source']


if __name__ == '__main__':
    _check_annotations_index()
    id = _create_codingjob({'name': 'test'})
    print(_get_codingjob(id))


