from flask import request, jsonify, Flask, g
from flask_httpauth import HTTPBasicAuth, HTTPTokenAuth, MultiAuth
from flask_cors import CORS

from http import HTTPStatus

from amcat4 import auth
from amcat4.auth import create_token
from amcat4.elastic import list_projects, create_project, setup_elastic

app = Flask(__name__)
CORS(app)

basic_auth = HTTPBasicAuth()
token_auth = HTTPTokenAuth()
multi_auth = MultiAuth(basic_auth, token_auth)


@basic_auth.verify_password
def verify_password(username, password):
    if username and auth.verify_user(username, password):
        g.email = username
        return True


@token_auth.verify_token
def verify_token(token):
    email = auth.verify_token(token)
    if email is not None:
        g.email = email
        return True


@app.route("/auth/token/", methods=['GET'])
@multi_auth.login_required
def get_token():
    """
    Create a new token for the authenticated user
    """
    token = create_token(g.email)
    return jsonify({"token": token})


@app.route("/projects/", methods=['GET'])
@multi_auth.login_required
def project_list():
    """
    List projects from this server
    """
    result = [{"name": name} for name in list_projects()]
    return jsonify(result)


@app.route("/projects/", methods=['POST'])
@multi_auth.login_required
def project_create():
    """
    Create a new project
    """
    data = request.get_json(force=True)
    name = data['name']
    create_project(name)
    return jsonify({"name": name}), HTTPStatus.CREATED


@app.route("/projects/<project_name>/documents", methods=['POST'])
@multi_auth.login_required
def upload_documents(project_name: str):
    """
    Upload documents to this server
    JSON payload should be a list of documents with at least a title, date, text and any optional attributes
    Note: The unique elastic ID will be the hash of title, date, text and url.
    """
    documents = request.get_json(force=True)
    result = upload_documents(project_name, documents)
    return jsonify(result)


@app.route("/projects/<project_name>/documents", methods=['GET'])
@multi_auth.login_required
def query_documents(project_name: str):
    """
    List or query documents in this project
    """
    documents = request.get_json(force=True)
    result = upload_documents(project_name, documents)
    return jsonify(result)


