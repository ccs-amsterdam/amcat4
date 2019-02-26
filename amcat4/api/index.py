import elasticsearch
from flask import Blueprint, jsonify, request, abort, g


from amcat4 import auth, query, aggregate, index, elastic
from amcat4.auth import Role
from amcat4.index import Index
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


@app_index.route("/index/<index>/documents", methods=['POST'])
@multi_auth.login_required
def upload_documents(index: str):
    """
    Upload documents to this server
    JSON payload should be a list of documents with at least a title, date, text and any optional attributes
    Note: The unique elastic ID will be the hash of title, date, text and url.
    """
    documents = request.get_json(force=True)
    result = elastic.upload_documents(index, documents)
    return jsonify(result), HTTPStatus.CREATED


@app_index.route("/index/<index>/documents/<docid>", methods=['GET'])
@multi_auth.login_required
def get_document(index: str, docid: str):
    """
    Get a single document by id
    """
    try:
        doc = elastic.get_document(index, docid)
        return jsonify(doc)
    except elasticsearch.exceptions.NotFoundError:
        abort(404)


@app_index.route("/index/<index>/fields", methods=['GET'])
@multi_auth.login_required
def get_fields(index: str):
    """
    Get the fields (columns) used in this index
    """
    r = elastic.get_fields(index)
    return jsonify(r)


@app_index.route("/index/<index>/fields/<field>/values", methods=['GET'])
@multi_auth.login_required
def get_values(index: str, field: str):
    """
    Get the fields (columns) used in this index
    """
    r = elastic.get_values(index, field)
    return jsonify(r)


