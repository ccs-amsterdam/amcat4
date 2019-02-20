from datetime import datetime, date

from flask.json import JSONEncoder
from flask import request, jsonify, Flask, g, abort
from flask_httpauth import HTTPBasicAuth, HTTPTokenAuth, MultiAuth
from flask_cors import CORS

from http import HTTPStatus

from werkzeug.exceptions import Unauthorized

from amcat4 import auth, query, aggregate
from amcat4 import elastic
from amcat4.auth import Role

app = Flask(__name__)


class MyJSONEncoder(JSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return super().default(o)


app.json_encoder = MyJSONEncoder
CORS(app)

basic_auth = HTTPBasicAuth()
token_auth = HTTPTokenAuth()
multi_auth = MultiAuth(basic_auth, token_auth)


def _bad_request(message):
    response = jsonify({'message': message})
    response.status_code = 400
    return response


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
    return jsonify({"token": token.decode('ascii')})


@app.route("/index/", methods=['GET'])
@multi_auth.login_required
def index_list():
    """
    List index from this server
    """
    result = [{"name": name} for name in elastic.list_indices()]
    return jsonify(result)


@app.route("/index/", methods=['POST'])
@multi_auth.login_required
def create_index():
    """
    Create a new index
    """
    check_role(ROLE_CREATOR)
    data = request.get_json(force=True)
    name = data['name']
    elastic.create_index(name)
    return jsonify({"name": name}), HTTPStatus.CREATED


@app.route("/index/<index>/documents", methods=['POST'])
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


@app.route("/index/<index>/fields", methods=['GET'])
@multi_auth.login_required
def get_fields(index: str):
    """
    Get the fields (columns) used in this index
    """
    r = elastic.get_fields(index)
    return jsonify(r)


@app.route("/index/<index>/fields/<field>/values", methods=['GET'])
@multi_auth.login_required
def get_values(index: str, field: str):
    """
    Get the fields (columns) used in this index
    """
    r = elastic.get_values(index, field)
    return jsonify(r)


@app.route("/index/<index>/query", methods=['GET'])
@multi_auth.login_required
def query_documents(index: str):
    """
    Query (or list) documents in this index. GET request parameters:
    q (or query_string)- Elastic query string
    sort - Comma separated list of fields to sort on, e.g. id,date:desc
    fields - Comma separated list of fields to return
    per_page - Number of results per page
    page - Page to fetch
    scroll - If given, create a new scroll_id to download all results in subsequent calls
    scroll_id - Get the next batch from this id.
    Any addition GET parameters are interpreted as filters, and can be
    field=value for a term query, or field__xxx=value for a range query, with xxx in gte, gt, lte, lt
    Note that dates can use relative queries, see elasticsearch 'date math'
    In case of conflict between field names and (other) arguments, you may prepend a field name with __
    If your field names contain __, it might be better to use POST queries
    """
    # [WvA] GET /documents might be more RESTful, but would not allow a POST query to the same endpoint
    args = {}
    KNOWN_ARGS = ["q", "sort", "page", "per_page", "scroll", "scroll_id", "fields"]
    for name in KNOWN_ARGS:
        if name in request.args:
            val = request.args[name]
            val = int(val) if name in ["page", "per_page"] else val
            val = val.split(",") if name in ["fields"] else val
            name = "query_string" if name == "q" else name
            args[name] = val
    filters = {}
    for (f, v) in request.args.items():
        if f not in KNOWN_ARGS:
            if f.startswith("__"):
                f = f[2:]
            if "__" in f:  # range query
                (field, operator) = f.split("__")
                if field not in filters:
                    filters[field] = {"range": {}}
                filters[field]['range'][operator] = v
            else:  # value query
                filters[f] = {"value": v}
    if filters:
        args['filters'] = filters
    r = query.query_documents(index, **args)
    if r is None:
        abort(404)
    return jsonify(r.as_dict())


@app.route("/index/<index>/query", methods=['POST'])
@multi_auth.login_required
def query_documents_post(index: str):
    """
    List or query documents in this index. POST body should be a json dict structured as follows (all keys optional):
    {param: value,   # for optional param in {sort, per_page, page, scroll, scroll_id, fields}
     'query_string': query   # elastic query_string, can be abbreviated to q
     'filters': {field: {'value': value},
                 field: {'range': {op: value [, op: value]}}  # for op in gte, gt, lte, lt
    }}
    """
    params = request.get_json(force=True)
    query_string = params.pop("query_string", None) or params.pop("q", None)
    filters = params.pop("filters", None)
    r = query.query_documents(index, query_string=query_string, filters=filters, **params)
    if r is None:
        abort(404)
    return jsonify(r.as_dict()), HTTPStatus.OK


@app.route("/index/<index>/aggregate", methods=['POST'])
@multi_auth.login_required
def query_aggregate_post(index: str):
    """
    Construct an aggregate query. POST body should be a json dict:
    {'axes': [{'field': .., ['interval': ..]}, ...],
     'filters': <filters, see query endpoint>
     }
    Will return a json list of lists [<axis-1-name>, ..., _n]
    """
    params = request.get_json(force=True)
    axes = params.pop('axes', [])
    if len(axes) < 1:
        return _bad_request('Aggregation axis not given')
    results = aggregate.query_aggregate(index, *axes, **params)
    return jsonify([b._asdict() for b in results])
