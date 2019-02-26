from flask import Blueprint, jsonify, request, abort


from amcat4 import query, aggregate
from http import HTTPStatus

from amcat4.api.common import multi_auth

app_query = Blueprint('app_query', __name__)


@app_query.route("/index/<index>/query", methods=['GET'])
@multi_auth.login_required
def query_documents(index: str):
    """
    Query (or list) documents in this index. GET request parameters:
    q - Elastic query string. Argument may be repeated for multiple queries (treated as OR)
    sort - Comma separated list of fields to sort on, e.g. id,date:desc
    fields - Comma separated list of fields to return
    per_page - Number of results per page
    page - Page to fetch
    scroll - If given, create a new scroll_id to download all results in subsequent calls
    scroll_id - Get the next batch from this id.
    Any additional GET parameters are interpreted as filters, and can be
    field=value for a term query, or field__xxx=value for a range query, with xxx in gte, gt, lte, lt
    Note that dates can use relative queries, see elasticsearch 'date math'
    In case of conflict between field names and (other) arguments, you may prepend a field name with __
    If your field names contain __, it might be better to use POST queries
    """
    # [WvA] GET /documents might be more RESTful, but would not allow a POST query to the same endpoint
    args = {}
    known_args = ["sort", "page", "per_page", "scroll", "scroll_id", "fields"]
    for name in known_args:
        if name in request.args:
            val = request.args[name]
            val = int(val) if name in ["page", "per_page"] else val
            val = val.split(",") if name in ["fields"] else val
            name = "queries" if name == "q" else name
            args[name] = val
    filters = {}
    for (f, v) in request.args.items():
        if f not in known_args + ["q"]:
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
    if "q" in request.args:
        args['queries'] = request.args.getlist("q")
    r = query.query_documents(index, **args)
    if r is None:
        abort(404)
    return jsonify(r.as_dict())


@app_query.route("/index/<index>/query", methods=['POST'])
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
    r = query.query_documents(index, **params)
    if r is None:
        abort(404)
    return jsonify(r.as_dict()), HTTPStatus.OK


@app_query.route("/index/<index>/aggregate", methods=['POST'])
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
        response = jsonify({'message': 'Aggregation axis not given'})
        response.status_code = 400
        return response
    results = aggregate.query_aggregate(index, *axes, **params)
    return jsonify([b._asdict() for b in results])
