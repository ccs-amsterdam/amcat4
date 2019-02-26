import elasticsearch
from flask import Blueprint, jsonify, request, abort, g

from amcat4 import elastic, index
from amcat4.auth import Role
from http import HTTPStatus

from amcat4.api.common import multi_auth, check_role

app_index = Blueprint('app_index', __name__)


@app_index.route("/index/", methods=['GET'])
@multi_auth.login_required
def index_list():
    """
    List index from this server. Returns a list of dicts containing name, role, and guest attributes
    """
    result = [dict(name=ix.name) for ix in (g.current_user.indices(include_guest=True))]
    return jsonify(result)


@app_index.route("/index/", methods=['POST'])
@multi_auth.login_required
def create_index():
    """
    Create a new index
    """
    check_role(Role.WRITER)
    data = request.get_json(force=True)
    name = data['name']
    ix = index.create_index(name, admin=g.current_user)
    return jsonify({'name': ix.name}), HTTPStatus.CREATED


@app_index.route("/index/<ix>/documents", methods=['POST'])
@multi_auth.login_required
def upload_documents(ix: str):
    """
    Upload documents to this server
    JSON payload should be a list of documents with at least a title, date, text and any optional attributes
    Note: The unique elastic ID will be the hash of title, date, text and url.
    """
    documents = request.get_json(force=True)
    result = elastic.upload_documents(ix, documents)
    return jsonify(result), HTTPStatus.CREATED


@app_index.route("/index/<ix>/documents/<docid>", methods=['GET'])
@multi_auth.login_required
def get_document(ix: str, docid: str):
    """
    Get a single document by id
    """
    try:
        doc = elastic.get_document(ix, docid)
        return jsonify(doc)
    except elasticsearch.exceptions.NotFoundError:
        abort(404)


@app_index.route("/index/<ix>/fields", methods=['GET'])
@multi_auth.login_required
def get_fields(ix: str):
    """
    Get the fields (columns) used in this index
    """
    r = elastic.get_fields(ix)
    return jsonify(r)


@app_index.route("/index/<ix>/fields/<field>/values", methods=['GET'])
@multi_auth.login_required
def get_values(ix: str, field: str):
    """
    Get the fields (columns) used in this index
    """
    r = elastic.get_values(ix, field)
    return jsonify(r)
