"""
API Endpoints for querying
"""

from http import HTTPStatus
from typing import Dict

from flask import Blueprint, jsonify, request, abort

from amcat4 import query, aggregate
from amcat4.aggregate import Axis, Aggregation
from amcat4.api.common import multi_auth, auto

app_query = Blueprint('app_query', __name__)


@app_query.route("/index/<index>/documents", methods=['GET'])
@auto.doc(group='Documents')
@multi_auth.login_required
def get_documents(index: str):
    """
    List (possibly filtered) documents in this index. GET request parameters:
    q - Elastic query string. Argument may be repeated for multiple queries (treated as OR)
    sort - Comma separated list of fields to sort on, e.g. id,date:desc
    fields - Comma separated list of fields to return
    per_page - Number of results per page
    page - Page to fetch
    scroll - If given, create a new scroll_id to download all results in subsequent calls
    scroll_id - Get the next batch from this id.
    highlight - add highlight tags <em>
    annotations - if true, also return _annotations with query matches as annotations

    Any additional GET parameters are interpreted as filters, and can be
    field=value for a term query, or field__xxx=value for a range query, with xxx in gte, gt, lte, lt
    Note that dates can use relative queries, see elasticsearch 'date math'
    In case of conflict between field names and (other) arguments, you may prepend a field name with __
    If your field names contain __, it might be better to use POST queries

    Returns a JSON object {data: [...], meta: {total_count, per_page, page_count, page|scroll_id}}
    """
    args = {}
    known_args = ["page", "per_page", "scroll", "scroll_id", "highlight", "annotations"]
    if "sort" in request.args:
        sort = [{x.replace(":desc", ""): "desc"} if x.endswith(":desc") else x
                for x in request.args["sort"].split(",")]
    else:
        sort = None
    fields = request.args["fields"].split(",") if "fields" in request.args else None
    for name in known_args:
        if name in request.args:
            val = request.args[name]
            if name in ["page", "per_page"]:
                val = int(val)
            args[name] = val
    filters: Dict[str, Dict] = {}
    for (f, v) in request.args.items():
        if f not in known_args + ["fields", "sort", "q"]:
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
    queries = request.args.getlist("q") if "q" in request.args else None
    r = query.query_documents(index, fields=fields, queries=queries, filters=filters, sort=sort, **args)
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
        # Sorting
        'sort': 'date'                        # sort by date
        'sort': ['date', 'id']                # sort by date, then by id
        'sort': [{'date': {'order':'desc'}}]  # sort by date in descending order (see elastic docs below)
        # Docs: https://www.elastic.co/guide/en/elasticsearch/reference/current/sort-search-results.html

        # Pagination
        'sort':
        'per_page': <number>            # Number of documents per page
        'page': <number>                # Request a specific page
        'scroll': <string>              # Create a scroll request. Value should be e.g. 5m for 5 minutes
        'scoll_id': <string>            # Get the next page for the scroll request

        # Control highlighting
        'annotations': true                        # Return _annotations with query matches as annotations
        'highglight': true                         # Highlight document. True highlights whole document
        'highlight': {'number of fragments': 3}    # Highlight up to 3 snippets per document (see elastic docs below)
        # Docs: https://www.elastic.co/guide/en/elasticsearch/reference/7.17/highlighting.html

        # select fields
        'fields': field                                    ## single field
        'fields': [field1, field2]                         ## multiple fields

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
    Construct an aggregate query. POST body should be a json dict with axes and/or aggregations keys,
    and optional filters and queries keys:
    :axes: list of dicts containing field and optional interval: [{'field': .., ['interval': ..]}, ...],
    :aggregations: list of dicts containing field, function, and optional name: [{field, function, [name]}, ...]
    :filters: see POST /query endpoint,
    :queries: see POST /query endpoint,
     }

    For example, to get average views per week per publisher
    {
     'axes': [{'field': 'date', 'interval':'week'}, {'field': 'publisher'}],
     'aggregations': [{'field': 'views', 'function': 'avg'}]
    }

    Returns a JSON object {data: [{axis1, ..., n, aggregate1, ...}, ...], meta: {axes: [...], aggregations: [...]}
    """
    params = request.get_json(force=True)
    axes = params.pop('axes', [])
    aggregations = params.pop('aggregations', [])
    if len(axes) + len(aggregations) < 1:
        response = jsonify({'message': 'Aggregation needs at least one axis or aggregation'})
        response.status_code = 400
        return response
    axes = [Axis(**x) for x in axes]
    aggregations = [Aggregation(**x) for x in aggregations]
    results = aggregate.query_aggregate(index, axes, aggregations, **params)
    return jsonify({"meta": {"axes": [axis.asdict() for axis in results.axes],
                             "aggregations": [a.asdict() for a in results.aggregations]},
                    "data": list(results.as_dicts())})
