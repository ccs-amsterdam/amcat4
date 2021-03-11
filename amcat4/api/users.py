from flask import Blueprint, jsonify, request, abort, g

from amcat4 import auth
from http import HTTPStatus

from amcat4.api.common import multi_auth, check_role, bad_request
from amcat4.auth import Role, User, hash_password

app_users = Blueprint('app_users', __name__)


@app_users.route("/users/", methods=['POST'])
@multi_auth.login_required
def create_user():
    """
    Create a new user. Request body should be a json with email, password, and optional (global) role
    """
    check_role(Role.WRITER)
    data = request.get_json(force=True)
    if User.select().where(User.email == data['email']).exists():
        return bad_request("User {} already exists".format(data['email']))
    role = data.get('global_role')
    if role:
        role = Role[role.upper()]
        if role == Role.ADMIN:
            check_role(Role.ADMIN)
        elif role != Role.WRITER:
            return bad_request("Global role should be ADMIN (superuser) or WRITER (staff/maintainer)")
    u = auth.create_user(email=data['email'], password=data['password'], global_role=role)
    return jsonify({"id": u.id, "email": u.email}), HTTPStatus.CREATED


@app_users.route("/users/<email>", methods=['GET'])
@multi_auth.login_required
def get_user(email):
    """
    View the current user. Users can view themselves, writer can view others
    """
    if g.current_user.email != email:
        check_role(Role.WRITER)
    try:
        u = User.get(User.email == email)
        return jsonify({"email": u.email, "global_role": u.role and u.role.name})
    except User.DoesNotExist:
        abort(404)


@app_users.route("/users/<email>", methods=['DELETE'])
@multi_auth.login_required
def delete_user(email):
    """
    Delete the given user. Users can delete themselves, admin can delete everyone, and writer can delete non-admin
    """
    if g.current_user.email != email:
        check_role(Role.WRITER)
    try:
        u = User.get(User.email == email)
    except User.DoesNotExist:
        abort(404)
    if u.role == Role.ADMIN:
        check_role(Role.ADMIN)
    u.delete_instance()
    return '', HTTPStatus.NO_CONTENT


@app_users.route("/users/<email>", methods=['PUT'])
@multi_auth.login_required
def modify_user(email):
    """
    Modify the given user.
    Users can modify themselves (but not their role), admin can change everyone, and writer can change non-admin.
    """
    if g.current_user.email != email:
        check_role(Role.WRITER)
    try:
        u = User.get(User.email == email)
    except User.DoesNotExist:
        abort(404)
    if u.role == Role.ADMIN:
        check_role(Role.ADMIN)
    data = request.get_json(force=True)
    if 'global_role' in data:
        role = Role[data['global_role'].upper()]
        check_role(role)  # need at least same level
        u.global_role = role
    if 'email' in data:
        u.email = data['email']
    if 'password' in data:
        u.password = hash_password(data['password'])
    u.save()
    return jsonify({"email": u.email, "global_role": u.role and u.role.name})


@app_users.route("/auth/token/", methods=['GET'])
@multi_auth.login_required
def get_token():
    """
    Create a new token for the authenticated user
    """
    token = g.current_user.create_token()
    return jsonify({"token": token.decode('ascii')})
