from flask import request, jsonify, Flask, g, abort
from flask_httpauth import HTTPBasicAuth, HTTPTokenAuth, MultiAuth
from flask_cors import CORS

from http import HTTPStatus

from werkzeug.exceptions import Unauthorized

from amcat4 import auth, query
from amcat4.auth import ROLE_CREATOR
from amcat4 import elastic

app = Flask(__name__)
CORS(app)

basic_auth = HTTPBasicAuth()
token_auth = HTTPTokenAuth()
multi_auth = MultiAuth(basic_auth, token_auth)


def check_role(role):
    u = g.current_user
    if not u:
        raise Unauthorized("No authenticated user")
    if not u.has_role(role):
        raise Unauthorized("User {} does not have role {}".format(u.email, role))


@basic_auth.verify_password
def verify_password(username, password):
    if not username:
        return False
    g.current_user = auth.verify_user(username, password)
    return g.current_user is not None


@token_auth.verify_token
def verify_token(token):
    g.current_user = auth.verify_token(token)
    return g.current_user is not None


@app.route("/auth/token/", methods=['GET'])
@multi_auth.login_required
def get_token():
    """
    Create a new token for the authenticated user
    """
    token = g.current_user.create_token()
    return jsonify({"token": token})


@app.route("/projects/", methods=['GET'])
@multi_auth.login_required
def project_list():
    """
    List projects from this server
    """
    result = [{"name": name} for name in elastic.list_projects()]
    return jsonify(result)


@app.route("/projects/", methods=['POST'])
@multi_auth.login_required
def project_create():
    """
    Create a new project
    """
    check_role(ROLE_CREATOR)
    data = request.get_json(force=True)
    name = data['name']
    elastic.create_project(name)
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
    result = elastic.upload_documents(project_name, documents)
    return jsonify(result), HTTPStatus.CREATED


@app.route("/projects/<project_name>/documents", methods=['GET'])
@multi_auth.login_required
def get_documents(project_name: str):
    """
    List or query documents in this project. GET request parameters:
    q - Elastic query string
    sort - Comma based list of fields to sort on, e.g. id,date:desc
    per_page - Number of results per page
    page - Page to fetch
    scroll - If given, create a new scroll_id to download all results in subsequent calls
    scroll_id - Get the next batch from this id. 
    """
    args = {}
    for name in ["q", "sort", "page", "per_page", "scroll", "scroll_id"]:
        if name in request.args:
            val = request.args[name]
            val = int(val) if name in ["page", "per_page"] else val
            name = "query_string" if name == "q" else name
            args[name] = val
    r = query.query_documents(project_name, **args)
    if r is None:
        abort(404)
    return jsonify(r.as_dict())


@app.route("/projects/<project_name>/fields", methods=['GET'])
@multi_auth.login_required
def get_fields(project_name: str):
    """
    Get the fields (columns) used in this project
    """
    r = elastic.get_fields(project_name)
    return jsonify(r)
