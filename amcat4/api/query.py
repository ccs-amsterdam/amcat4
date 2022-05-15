"""
API Endpoints for querying
"""

from typing import Dict, List, Optional, Any, Union, Iterable, Tuple

from fastapi import APIRouter, HTTPException, status, Request, Query, Depends
from fastapi.params import Body
from pydantic.main import BaseModel

from amcat4 import query, aggregate
from amcat4.aggregate import Axis, Aggregation
from amcat4.api.auth import authenticated_user
from amcat4.auth import User

app_query = APIRouter(
    prefix="/index",
    tags=["query"])


class QueryMeta(BaseModel):
    total_count: int
    per_page: Optional[int]
    page_count: Optional[int]
    page: Optional[int]
    scroll_id: Optional[str]


class QueryResult(BaseModel):
    results: List[Dict[str, Any]]
    meta: QueryMeta


@app_query.get("/{index}/documents", response_model=QueryResult)
def get_documents(index: str,
                  request: Request,
                  q: List[str] = Query(None, description="Elastic query string. "
                                       "Argument may be repeated for multiple queries (treated as OR)"),
                  sort: str = Query(None,
                                    description="Comma separated list of fields to sort on",
                                    example="id,date:desc", regex=r"\w+(:desc)?(,\w+(:desc)?)*"),
                  fields: str = Query(None, description="Comma separated list of fields to return",
                                      regex=r"\w+(,\w+)*"),
                  per_page: int = Query(None, description="Number of results per page"),
                  page: int = Query(None, description="Page to fetch"),
                  scroll: str = Query(None,
                                      description="Create a new scroll_id to download all results in subsequent calls",
                                      example="3m"),
                  scroll_id: str = Query(None, description="Get the next batch from this scroll id"),
                  highlight: bool = Query(False, description="add highlight tags <em>"),
                  annotations: bool = Query(False, description="if true, also return _annotations "
                                                               "with query matches as annotations"),
                  user: User = Depends(authenticated_user)):
    """
    List (possibly filtered) documents in this index.

    Any additional GET parameters are interpreted as filters, and can be
    field=value for a term query, or field__xxx=value for a range query, with xxx in gte, gt, lte, lt
    Note that dates can use relative queries, see elasticsearch 'date math'
    In case of conflict between field names and (other) arguments, you may prepend a field name with __
    If your field names contain __, it might be better to use POST queries

    Returns a JSON object {data: [...], meta: {total_count, per_page, page_count, page|scroll_id}}
    """
    args = {}
    sort = sort and [{x.replace(":desc", ""): "desc"} if x.endswith(":desc") else x
                     for x in sort.split(",")]
    fields = fields and fields.split(",")
    known_args = ["page", "per_page", "scroll", "scroll_id", "highlight", "annotations"]
    for name in known_args:
        val = locals()[name]
        if val:
            args[name] = int(val) if name in ["page", "per_page"] else val
    filters: Dict[str, Dict] = {}
    for (f, v) in request.query_params.items():
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
    r = query.query_documents(index, fields=fields, queries=q, filters=filters, sort=sort, **args)
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No results")
    return r.as_dict()


FilterValue = Union[str, int]


class FilterSpec(BaseModel):
    values: Optional[List[FilterValue]]
    gt: Optional[FilterValue]
    lt: Optional[FilterValue]
    gte: Optional[FilterValue]
    lte: Optional[FilterValue]
    exists: Optional[bool]


def _process_queries(queries: Optional[Union[str, List[str], List[Dict[str, str]]]] = None) -> Optional[dict]:
    """Convert query json to dict format: {label1:query1, label2: query2}  uses indices if no labels given"""
    if queries:
        # to dict format: {label1:query1, label2: query2}  uses indices if no labels given
        if isinstance(queries, str):
            queries = [queries]
        if isinstance(queries, list):
            queries = {str(i): q for i, q in enumerate(queries)}
        return queries


def _process_filters(filters: Optional[Dict[str, Union[FilterValue, List[FilterValue], FilterSpec]]] = None
                     ) -> Iterable[Tuple[str, dict]]:
    """Convert filters to dict format: {field: {values: []}}"""
    if not filters:
        return
    for field, filter_ in filters.items():
        if isinstance(filter_, str):
            filter_ = [filter_]
        if isinstance(filter_, list):
            yield field, {'values': filter_}
        elif isinstance(filter_, FilterSpec):
            yield field, {k: v for (k, v) in filter_.dict().items() if v is not None}
        else:
            raise ValueError(f"Cannot parse filter: {filter_}")


@app_query.post("/{index}/query", response_model=QueryResult)
def query_documents_post(
    index: str,
    queries: Optional[Union[str, List[str], Dict[str, str]]] = Body(
        None, description="Query/Queries to run. Value should be a single query string, a list of query strings, "
                          "or a dict of {'label': 'query'}"
    ),
    fields: Optional[List[str]] = Body(None, description="List of fields to retrieve for each document"),
    filters: Optional[Dict[str, Union[FilterValue, List[FilterValue], FilterSpec]]] = Body(
        None, description="Field filters, should be a dict of field names to filter specifications,"
                          "which can be either a value, a list of values, or a FilterSpec dict"),
    sort: Optional[Union[str, List[str], List[Dict[str, dict]]]] = Body(
        None, description="Sort by field name(s) or dict (see "
        "https://www.elastic.co/guide/en/elasticsearch/reference/current/sort-search-results.html for dict format)",
        examples={"simple": {"summary": "Sort by single field", "value": "'date'"},
                  "multiple": {"summary": "Sort by multiple fields", "value": "['date', 'title']"},
                  "dict": {"summary": "Use dict to specify sort options", "value": " [{'date': {'order':'desc'}}]"},
                  }),
    per_page: Optional[int] = Body(10, description="Number of documents per page"),
    page: Optional[int] = Body(0, description="Which page to retrieve"),
    scroll: Optional[str] = Body(
        None, description="Scroll specification (e.g. '5m') to start a scroll request"
                          "This will return a scroll_id which should be passed to subsequent calls"
                          "(this is the advised way of scrolling through multiple pages of results)", example="5m"),
    scroll_id: Optional[str] = Body(None, description="Scroll id from previous response to continue scrolling"),
    annotations: Optional[bool] = Body(None, description="Return _annotations with query matches as annotations"),
    highlight: Optional[Union[bool, Dict]] = Body(
        None, description="Highlight document. 'true' highlights whole document, see elastic docs for dict format"
                          "https://www.elastic.co/guide/en/elasticsearch/reference/7.17/highlighting.html"),

        user: User = Depends(authenticated_user)
):
    """
    List or query documents in this index.

    Returns a JSON object {data: [...], meta: {total_count, per_page, page_count, page|scroll_id}}
    """
    # TODO check user rights on index
    # Standardize fields, queries and filters to their most versatile format
    if fields:
        # to array format: fields: [field1, field2]
        if isinstance(fields, str):
            fields = [fields]
    queries = _process_queries(queries)
    filters = dict(_process_filters(filters))
    r = query.query_documents(index, queries=queries, filters=filters, fields=fields,
                              sort=sort, per_page=per_page, page=page, scroll_id=scroll_id, scroll=scroll,
                              annotations=annotations, highlight=highlight)
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No results")
    return r.as_dict()


class AggregationSpec(BaseModel):
    # TODO: can probably merge wth Aggregation class?
    field: str
    function: str
    name: Optional[str]


class AxisSpec(BaseModel):
    # TODO: can probably merge wth Axis class?
    field: str
    interval: Optional[str]


@app_query.post("/{index}/aggregate")
def query_aggregate_post(
        index: str,
        axes: Optional[List[AxisSpec]] = Body(None, description="Axes to aggregate on (i.e. group by)"),
        aggregations: Optional[List[AggregationSpec]] = Body(None, description="Aggregate functions to compute"),
        queries: Optional[Union[str, List[str], Dict[str, str]]] = Body(
            None, description="Query/Queries to run. Value should be a single query string, a list of query strings, "
                              "or a dict of queries {'label': 'query'}"
        ),
        filters: Optional[Dict[str, Union[FilterValue, List[FilterValue], FilterSpec]]] = Body(
            None, description="Field filters, should be a dict of field names to filter specifications,"
                              "which can be either a value, a list of values, or a FilterSpec dict"),
        user: User = Depends(authenticated_user)):
    """
    Construct an aggregate query.

    For example, to get average views per week per publisher
    {
     'axes': [{'field': 'date', 'interval':'week'}, {'field': 'publisher'}],
     'aggregations': [{'field': 'views', 'function': 'avg'}]
    }

    Returns a JSON object {data: [{axis1, ..., n, aggregate1, ...}, ...], meta: {axes: [...], aggregations: [...]}
    """
    # TODO check user rights on index
    _axes = [Axis(**x.dict()) for x in axes] if axes else []
    _aggregations = [Aggregation(**x.dict()) for x in aggregations] if aggregations else []
    if not (_axes or _aggregations):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='Aggregation needs at least one axis or aggregation')
    queries = _process_queries(queries)
    filters = dict(_process_filters(filters))
    results = aggregate.query_aggregate(index, _axes, _aggregations, queries=queries, filters=filters)
    return {"meta": {"axes": [axis.asdict() for axis in results.axes],
                     "aggregations": [a.asdict() for a in results.aggregations]},
            "data": list(results.as_dicts())}
