"""
AmCAT4 can use either Basic or Token-based authentication.
A client can request a token with basic authentication and store that token for future requests.
"""

from flask import Blueprint, jsonify, request, abort, g

from amcat4 import auth
from http import HTTPStatus

from amcat4.api.common import multi_auth, check_role, bad_request, auto
from amcat4.auth import Role, User, hash_password
from amcat4.api.index import _index

app_users = Blueprint('app_users', __name__)


@app_users.route("/users/", methods=['POST'])
@auto.doc(group='users')
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
    if (data.get('index_access')):
        _index(data.get('index')).set_role(u, Role[data.get('global_role')])
    return jsonify({"id": u.id, "email": u.email}), HTTPStatus.CREATED


@app_users.route("/users/<email>", methods=['GET'])
@auto.doc(group='users')
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


@app_users.route("/users/all", methods=['GET'])
@auto.doc(group='users')
@multi_auth.login_required
def get_users():
    check_role(Role.ADMIN)
    try:
        result=[]
        res1 = [dict(user=u.email, role=u.global_role) for u in User.select()]
        for entry in res1:
            for ix, role in User.get(User.email == entry['user']).indices().items():
                result.append(dict(user= entry['user'], index_name= ix.name, role=role.name))
        return jsonify(result)
    except User.DoesNotExist:
        abort(404)


@app_users.route("/users/<email>", methods=['DELETE'])
@auto.doc(group='users')
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
@auto.doc(group='users')
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
    print(data)
    if 'global_role' in data:
        role = Role[data['global_role'].upper()]
        check_role(role)  # need at least same level
        u.global_role = role
        _index(data.get('index')).set_role(u, Role[data.get('global_role')])
    if 'email' in data:
        u.email = data['email']
    if 'password' in data:
        u.password = hash_password(data['password'])
    u.save()
    return jsonify({"email": u.email, "global_role": u.role and u.role.name})


@app_users.route("/auth/token/", methods=['GET'])
@auto.doc(group='auth')
@multi_auth.login_required
def get_token():
    """
    Create a new token for the authenticated user
    """
    token = g.current_user.create_token()
    return jsonify({"token": token.decode('ascii')})
