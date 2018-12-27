import logging

from flask import request, jsonify, Flask, g
from flask_httpauth import HTTPBasicAuth, HTTPTokenAuth, MultiAuth

from http import HTTPStatus

from amcat4 import auth
from amcat4.auth import create_token
from amcat4.elastic import list_projects, create_project, setup_elastic

app = Flask(__name__)

basic_auth = HTTPBasicAuth()
token_auth = HTTPTokenAuth()
multi_auth = MultiAuth(basic_auth, token_auth)


@basic_auth.verify_password
def verify_password(username, password):
    if auth.verify_user(username, password):
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


if __name__ == '__main__':
    logging.basicConfig(format='[%(levelname)-7s:%(name)-15s] %(message)s', level=logging.INFO)
    setup_elastic()
    if not auth.has_user():
        logging.warning("**** No user detected, creating superuser admin:admin ****")
        auth.create_user("admin", "admin", roles=[auth.ROLE_ADMIN], check_email=False)
    app.run(debug=True)
