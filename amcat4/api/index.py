import elasticsearch
from flask import Blueprint, jsonify, request, abort, g

from amcat4 import elastic, index
from amcat4.auth import Role
from http import HTTPStatus

from amcat4.api.common import multi_auth, check_role
from amcat4.index import Index

app_index = Blueprint('app_index', __name__)


def _index(ix: str) -> Index:
    try:
        return Index.get(Index.name == ix)
    except Index.DoesNotExist:
        abort(404)


def index_json(ix: Index):
    return jsonify({'name': ix.name, 'guest_role': ix.guest_role and Role(ix.guest_role).name})


@app_index.route("/index/", methods=['GET'])
@multi_auth.login_required
def index_list():
    """
    List index from this server. Returns a list of dicts containing name, role, and guest attributes
    """
    result = [dict(name=ix.name, role=role.name) for ix, role in g.current_user.indices(include_guest=True).items()]
    return jsonify(result)


@app_index.route("/index/", methods=['POST'])
@multi_auth.login_required
def create_index():
    """
    Create a new index, setting the current user to admin (owner).
    POST data should be json containing name and optional guest_role
    """
    check_role(Role.WRITER)
    data = request.get_json(force=True)
    name = data['name']
    guest_role = Role[data['guest_role'].upper()] if 'guest_role' in data else None
    ix = index.create_index(name, admin=g.current_user, guest_role=guest_role)
    return index_json(ix), HTTPStatus.CREATED


@app_index.route("/index/<ix>", methods=['PUT'])
@multi_auth.login_required
def modify_index(ix: str):
    """
    Modify the index. Currently only supports modifying guest_role
    POST data should be json containing the changed values (i.e. guest_role)
    """
    ix = _index(ix)
    check_role(Role.WRITER, ix)
    data = request.get_json(force=True)
    if 'guest_role' in data:
        guest_role = Role[data['guest_role'].upper()] if data['guest_role'] else None
        if guest_role == Role.ADMIN:
            check_role(Role.ADMIN, ix)
        ix.guest_role = guest_role
    ix.save()
    return index_json(ix)


@app_index.route("/index/<ix>", methods=['GET'])
@multi_auth.login_required
def view_index(ix: str):
    """
    Modify the index. Currently only supports modifying guest_role
    POST data should be json containing the changed values (i.e. guest_role)
    """
    ix = _index(ix)
    check_role(Role.METAREADER, ix)
    return index_json(ix)


@app_index.route("/index/<ix>", methods=['DELETE'])
@multi_auth.login_required
def delete_index(ix: str):
    """
    Delete the index.
    """
    ix = _index(ix)
    check_role(Role.ADMIN, ix)
    ix.delete_index()
    return "", HTTPStatus.NO_CONTENT



@app_index.route("/index/<ix>/documents", methods=['POST'])
@multi_auth.login_required
def upload_documents(ix: str):
    """
    Upload documents to this server
    JSON payload should be a list of documents with at least a title, date, text and any optional attributes
    Note: The unique elastic ID will be the hash of title, date, text and url.
    """
    check_role(Role.WRITER, _index(ix))
    documents = request.get_json(force=True)
    result = elastic.upload_documents(ix, documents)
    return jsonify(result), HTTPStatus.CREATED


@app_index.route("/index/<ix>/documents/<docid>", methods=['GET'])
@multi_auth.login_required
def get_document(ix: str, docid: str):
    """
    Get a single document by id
    GET request parameters:
    fields - Comma separated list of fields to return (default: all fields)
    """
    check_role(Role.READER, _index(ix))
    kargs = {}
    if 'fields' in request.args:
        kargs['_source'] = request.args['fields']
    try:
        doc = elastic.get_document(ix, docid, **kargs)
    except elasticsearch.exceptions.NotFoundError:
        abort(404)
    return jsonify(doc)


@app_index.route("/index/<ix>/documents/<docid>", methods=['PUT'])
@multi_auth.login_required
def update_document(ix: str, docid: str):
    """
    Update a document
    PUT request body should be a json {field: value} mapping of fields to update
    """

    check_role(Role.WRITER, _index(ix))
    update = request.get_json(force=True)
    try:
        elastic.update_document(ix, docid, update)
    except elasticsearch.exceptions.NotFoundError:
        abort(404)
    return '', HTTPStatus.OK


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
