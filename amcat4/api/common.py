import logging
from datetime import datetime, date

from flask import g, json, jsonify
from flask_httpauth import HTTPBasicAuth, HTTPTokenAuth, MultiAuth
from werkzeug.exceptions import Unauthorized

from amcat4 import auth
from amcat4.auth import Role
from amcat4.index import Index

basic_auth = HTTPBasicAuth()
token_auth = HTTPTokenAuth()
multi_auth = MultiAuth(basic_auth, token_auth)


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


def check_role(role: Role, ix: Index = None):
    u = g.current_user
    logging.warning(f">>> u:{u}, role:{role}, ix:{ix}")
    if not u:
        raise Unauthorized("No authenticated user")
    if ix:
        if not ix.has_role(u, role):
            raise Unauthorized("User {} does not have role {} on index {}".format(u.email, role, ix))
    else:
        if not u.has_role(role):
            raise Unauthorized("User {} does not have role {}".format(u.email, role))


class MyJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return super().default(o)


def bad_request(message):
    response = jsonify({'message': message})
    response.status_code = 400
    return response
