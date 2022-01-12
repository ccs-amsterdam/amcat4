"""
API Endpoints for querying
"""

from http import HTTPStatus

from flask import Blueprint, jsonify, request, abort

from amcat4 import query, aggregate
from amcat4.api.common import multi_auth, auto

app_query = Blueprint('app_query', __name__)


@app_query.route("/index/<index>/query", methods=['GET'])
@auto.doc(group='Querying')
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
    highlight - if true, add highlight tags <em>
    annotations - if true, also return _annotations with query matches as annotations

    Returns a JSON object {data: [...], meta: {total_count, per_page, page_count, page|scroll_id}}
    """
    # [WvA] GET /documents might be more RESTful, but would not allow a POST query to the same endpoint
    args = {}
    known_args = ["sort", "page", "per_page", "scroll", "scroll_id", "fields", "highlight", "annotations"]
    for name in known_args:
        if name in request.args:
            val = request.args[name]
            val = int(val) if name in ["page", "per_page"] else val
            val = val.split(",") if name in ["fields"] else val
            args[name] = val

    filters = {}
    for (f, v) in request.args.items():
        if f not in known_args + ["q"]:
            if f.startswith("__"):
                f = f[2:]
            if "__" in f:  # range query
                (field, operator) = f.split("__")
                if field not in filters:
                    filters[field] = {}
                filters[field][operator] = v
            else:  # value query
                if f not in filters:
                    filters[f] = {'values': []}
                filters[f]['values'].append(v)

    if filters:
        args['filters'] = filters
    if "q" in request.args:
        args['queries'] = request.args.getlist("q")
    r = query.query_documents(index, **args)
    if r is None:
        abort(404)
    return jsonify(r.as_dict())


@app_query.route("/index/<index>/query", methods=['POST'])
@auto.doc(group='Querying')
@multi_auth.login_required
def query_documents_post(index: str):
    """
    List or query documents in this index. POST body should be a json dict structured as follows (all keys optional):


    {
        # for optional param in {sort, per_page, page, scroll, scroll_id, highlight, annotations}
        param: value,

        # select fields
        fields: field                                    ## single field
        fields: [field1, field2]                         ## multiple fields

        # elastic queries.
        'queries':  query,                               ## single query
        'queries': [query1, query2],                     ## OR without labels
        'queries': {label1: query1, label2: query2}      ## OR with labels

        # filters
        'filters': {field: value},                       ## exact value
                   {field: [value1, value2]},            ## OR
                   {field: {gt(e): value, lt(e): value}  ## range or multiple
                   {field: {values: [v1,v2]}             ## can also use values inside dict
        }
    }

    Returns a JSON object {data: [...], meta: {total_count, per_page, page_count, page|scroll_id}}
    }

    """
    params = request.get_json(force=True)

    # first standardize fields, queries and filters to their most versatile format
    if 'fields' in params:
        # to array format: fields: [field1, field2]
        if isinstance(params['fields'], str):
            params['fields'] = [params['fields']]

    if 'queries' in params:
        # to dict format: {label1:query1, label2: query2}  uses indices if no labels given
        if isinstance(params['queries'], str):
            params['queries'] = [params['queries']]
        if isinstance(params['queries'], list):
            params['queries'] = {str(i): q for i, q in enumerate(params['queries'])}

    if 'filters' in params:
        # to dict format: {field: {values: []}}
        for field, filter in params['filters'].items():
            if isinstance(filter, str):
                filter = [filter]
            if isinstance(filter, list):
                params['filters'][field] = {'values': filter}

    r = query.query_documents(index, **params)
    if r is None:
        abort(404)
    return jsonify(r.as_dict()), HTTPStatus.OK


@app_query.route("/index/<index>/aggregate", methods=['POST'])
@auto.doc(group='Querying')
@multi_auth.login_required
def query_aggregate_post(index: str):
    """
    Construct an aggregate query. POST body should be a json dict:
    {'axes': [{'field': .., ['interval': ..]}, ...],
     'filters': <filters, see query endpoint>
     }

    Returns a JSON object {data: [{axis1, ..., n}, ...], meta: {axes: [...]}
    """
    params = request.get_json(force=True)
    axes = params.pop('axes', [])
    if len(axes) < 1:
        response = jsonify({'message': 'Aggregation axis not given'})
        response.status_code = 400
        return response
    axes, results = aggregate.query_aggregate(index, *axes, **params)
    return jsonify({"meta": {"axes": [axis.asdict() for axis in axes]},
                    "data": [b._asdict() for b in results]})
