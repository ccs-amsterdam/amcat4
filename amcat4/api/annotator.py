from typing import Optional

from flask import Blueprint, jsonify, request, abort, make_response
from werkzeug.exceptions import HTTPException

from amcat4.api.common import multi_auth, check_role
from amcat4.auth import Role
from amcat4.elastic import es

app_annotator = Blueprint('app_annotator', __name__)

"""
A coding job consists of the following information:
{
 "config": {
   "rules": ..,
   ..
 },
 "codebook": ..,
 "units": [{
     "content": ..,
     "annotations": {"user_id": .., ..}  
   }, ... ]
}

The codebook is an arbitrary json object that is used by the coding interface.
Similarly, the content and annotations fields of units are arbitrary json objects
used by the coding interface and researcher.

The config dict is used by the server to control which units to serve for annotation,
how to authenticate coders, and whether to post the results back to a (e.g. AmCAT) server.  
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
    #TODO: authenticate the user (e.g. using bearer token)
    user = request.args.get('user')
    if not user:
        abort(401)
    job = _get_codingjob(id)
    best = None  # (i, min_n_coded, unit)
    for i, unit in enumerate(job['units']):
        coders = set(unit.get("annotations", {}).keys())
        if user not in coders:
            if best is None or len(coders) < best[0]:
                best = len(coders), i, unit
    if best:
        return {'id': best[1], 'unit': best[2]}
    abort(404)

@app_annotator.route("/codingjob/<job_id>/unit/<unit_id>/annotation", methods=['POST'])
def set_annotation(job_id, unit_id):
    """Set the annotations for a specific unit"""
    #TODO: authenticate the user (e.g. using bearer token)
    user = request.args.get('user')
    if not user:
        abort(401)
    job = _get_codingjob(job_id)
    annotations = request.get_json(force=True)
    try:
        unit = job["units"][int(unit_id)]
    except (ValueError, IndexError):
        abort(404)  # unit did not exist or was not integer
    if "annotations" not in unit:
        unit["annotations"] = {}
    unit["annotations"][user] = annotations
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


