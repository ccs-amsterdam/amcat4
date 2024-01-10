"""API Endpoints for querying."""

from typing import Dict, List, Optional, Any, Union, Iterable, Tuple, Literal

from fastapi import APIRouter, HTTPException, status, Request, Query, Depends, Response
from fastapi.params import Body
from pydantic.main import BaseModel

from amcat4 import elastic, query, aggregate
from amcat4.aggregate import Axis, Aggregation
from amcat4.api.auth import authenticated_user, check_fields_access
from amcat4.index import Role, get_role
from amcat4.query import update_tag_query
from amcat4.util import parse_field

app_query = APIRouter(prefix="/index", tags=["query"])


class QueryMeta(BaseModel):
    """Form for query metadata."""

    total_count: int
    per_page: Optional[int] = None
    page_count: Optional[int] = None
    page: Optional[int] = None
    scroll_id: Optional[str] = None


class QueryResult(BaseModel):
    """Form for query results."""

    results: List[Dict[str, Any]]
    meta: QueryMeta


def get_or_validate_allowed_fields(
    user: str, indices: Iterable[str], fields: Iterable[str] = None
):
    """
    For any endpoint that returns field values, make sure the user only gets fields that
    they are allowed to see. If fields is None, return all allowed fields. If fields is not None,
    check whether the user can access the fields (If not, raise an error).
    """

    if not isinstance(user, str):
        raise ValueError("User should be a string")
    if not isinstance(indices, list):
        raise ValueError("Indices should be a list")
    if fields is not None and not isinstance(fields, list):
        raise ValueError("Fields should be a list or None")

    if fields is None:
        if len(indices) > 1:
            # this restrictions is needed, because otherwise we need to return all allowed fields taking
            # into account the user's role for each index, and take the lowest possible access.
            # this is error prone and complex, so best to just disallow it. Also, requesting all fields
            # for multiple indices is probably not something we should support anyway
            raise ValueError("Fields should be specified if multiple indices are given")
        index_fields = elastic.get_fields(indices[0])
        role = get_role(indices[0], user)
        all_fields = []
        for field in index_fields.keys():
            if role >= Role.READER:
                all_fields.append(field)
            elif role == Role.METAREADER:
                field_meta: dict = index_fields[field].get("meta", {})
                metareader_access = field_meta.get("metareader_access", None)
                if metareader_access == "read":
                    all_fields.append(field)
                elif "snippet" in metareader_access:
                    _, nomatch_chars, max_matches, match_chars = parse_field(
                        metareader_access
                    )
                    all_fields.append(
                        f"{field}[{nomatch_chars};{max_matches};{match_chars}]"
                    )
            else:
                raise HTTPException(
                    status_code=401,
                    detail=f"User {user} does not have a role on index {indices[0]}",
                )

    else:
        for index in indices:
            check_fields_access(index, user, fields)
        return fields


@app_query.get("/{index}/documents", response_model=QueryResult)
def get_documents(
    index: str,
    request: Request,
    q: List[str] = Query(
        None,
        description="Elastic query string. "
        "Argument may be repeated for multiple queries (treated as OR)",
    ),
    sort: str = Query(
        None,
        description="Comma separated list of fields to sort on",
        examples="id,date:desc",
        pattern=r"\w+(:desc)?(,\w+(:desc)?)*",
    ),
    fields: str = Query(
        None,
        description="Comma separated list of fields to return. "
        "You can also request a snippet of a field by appending the suffix [nomatch_chars;max_matches;match_chars]. "
        "'matches' here refers to words from text queries. If there is no query, the snippet is the first [nomatch_chars] characters. "
        "If there is a query, snippets are returned for up to [max_matches] matches, with each match having [match_chars] "
        "characters. If there are multiple matches, they are concatenated with ' ... '.",
        pattern=r"\w+(,\w+)*",
    ),
    highlight: bool = Query(False, description="If true, highlight fields"),
    per_page: int = Query(None, description="Number of results per page"),
    page: int = Query(None, description="Page to fetch"),
    scroll: str = Query(
        None,
        description="Create a new scroll_id to download all results in subsequent calls",
        examples="3m",
    ),
    scroll_id: str = Query(None, description="Get the next batch from this scroll id"),
    user: str = Depends(authenticated_user),
):
    """
    List (possibly filtered) documents in this index.

    Any additional GET parameters are interpreted as filters, and can be
    field=value for a term query, or field__xxx=value for a range query, with xxx in gte, gt, lte, lt
    Note that dates can use relative queries, see elasticsearch 'date math'
    In case of conflict between field names and (other) arguments, you may prepend a field name with __
    If your field names contain __, it might be better to use POST queries

    Returns a JSON object {data: [...], meta: {total_count, per_page, page_count, page|scroll_id}}
    """
    indices = index.split(",")
    fields = fields and fields.split(",")
    fields = get_or_validate_allowed_fields(user, indices, fields)
    for index in indices:
        check_fields_access(index, user, fields)

    args = {}
    sort = sort and [
        {x.replace(":desc", ""): "desc"} if x.endswith(":desc") else x
        for x in sort.split(",")
    ]
    known_args = ["page", "per_page", "scroll", "scroll_id", "highlight"]
    for name in known_args:
        val = locals()[name]
        if val:
            args[name] = int(val) if name in ["page", "per_page"] else val
    filters: Dict[str, Dict] = {}
    for f, v in request.query_params.items():
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
                    filters[f] = {"values": []}
                filters[f]["values"].append(v)
    r = query.query_documents(
        indices, fields=fields, queries=q, filters=filters, sort=sort, **args
    )
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No results")
    return r.as_dict()


FilterValue = Union[str, int]


class FilterSpec(BaseModel):
    """Form for filter specification."""

    values: Optional[List[FilterValue]] = None
    gt: Optional[FilterValue] = None
    lt: Optional[FilterValue] = None
    gte: Optional[FilterValue] = None
    lte: Optional[FilterValue] = None
    exists: Optional[bool] = None


def _process_queries(
    queries: Optional[Union[str, List[str], List[Dict[str, str]]]] = None
) -> Optional[dict]:
    """Convert query json to dict format: {label1:query1, label2: query2} uses indices if no labels given."""
    if queries:
        # to dict format: {label1:query1, label2: query2}  uses indices if no labels given
        if isinstance(queries, str):
            queries = [queries]
        if isinstance(queries, list):
            queries = {str(i): q for i, q in enumerate(queries)}
        return queries


def _process_filters(
    filters: Optional[
        Dict[str, Union[FilterValue, List[FilterValue], FilterSpec]]
    ] = None
) -> Iterable[Tuple[str, dict]]:
    """Convert filters to dict format: {field: {values: []}}."""
    if not filters:
        return
    for field, filter_ in filters.items():
        if isinstance(filter_, str):
            filter_ = [filter_]
        if isinstance(filter_, list):
            yield field, {"values": filter_}
        elif isinstance(filter_, FilterSpec):
            yield field, {
                k: v for (k, v) in filter_.model_dump().items() if v is not None
            }
        else:
            raise ValueError(f"Cannot parse filter: {filter_}")


@app_query.post("/{index}/query", response_model=QueryResult)
def query_documents_post(
    index: str,
    queries: Optional[Union[str, List[str], Dict[str, str]]] = Body(
        None,
        description="Query/Queries to run. Value should be a single query string, a list of query strings, "
        "or a dict of {'label': 'query'}",
    ),
    fields: Optional[List[str]] = Body(
        None,
        description="List of fields to retrieve for each document"
        "You can also request a snippet of a field by adding snippet parameters between brackets: "
        "fieldname[nomatch_chars;max_matches;match_chars]. 'matches' here refers to words from text queries. "
        "If there is no query, the snippet is the first [nomatch_chars] characters. "
        "If there is a query, snippets are returned for up to [max_matches] matches, with each match having [match_chars] "
        "characters. If there are multiple matches, they are concatenated with ' ... '.",
    ),
    filters: Optional[
        Dict[str, Union[FilterValue, List[FilterValue], FilterSpec]]
    ] = Body(
        None,
        description="Field filters, should be a dict of field names to filter specifications,"
        "which can be either a value, a list of values, or a FilterSpec dict",
    ),
    sort: Optional[Union[str, List[str], List[Dict[str, dict]]]] = Body(
        None,
        description="Sort by field name(s) or dict (see "
        "https://www.elastic.co/guide/en/elasticsearch/reference/current/sort-search-results.html for dict format)",
        examples={
            "simple": {"summary": "Sort by single field", "value": "'date'"},
            "multiple": {
                "summary": "Sort by multiple fields",
                "value": "['date', 'title']",
            },
            "dict": {
                "summary": "Use dict to specify sort options",
                "value": " [{'date': {'order':'desc'}}]",
            },
        },
    ),
    per_page: Optional[int] = Body(10, description="Number of documents per page"),
    page: Optional[int] = Body(0, description="Which page to retrieve"),
    scroll: Optional[str] = Body(
        None,
        description="Scroll specification (e.g. '5m') to start a scroll request"
        "This will return a scroll_id which should be passed to subsequent calls"
        "(this is the advised way of scrolling through multiple pages of results)",
        examples="5m",
    ),
    scroll_id: Optional[str] = Body(
        None, description="Scroll id from previous response to continue scrolling"
    ),
    highlight: Optional[bool] = Body(False, description="If true, highlight fields"),
    user=Depends(authenticated_user),
):
    """
    List or query documents in this index.

    Returns a JSON object {data: [...], meta: {total_count, per_page, page_count, page|scroll_id}}
    """
    # TODO check user rights on index
    # Standardize fields, queries and filters to their most versatile format
    indices = index.split(",")
    fields = [fields] if isinstance(fields, str) else fields
    fields = get_or_validate_allowed_fields(user, indices, fields)

    queries = _process_queries(queries)
    filters = dict(_process_filters(filters))
    r = query.query_documents(
        indices,
        queries=queries,
        filters=filters,
        fields=fields,
        sort=sort,
        per_page=per_page,
        page=page,
        scroll_id=scroll_id,
        scroll=scroll,
        highlight=highlight,
    )
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No results")
    return r.as_dict()


class AggregationSpec(BaseModel):
    """Form for an aggregation."""

    # TODO: can probably merge wth Aggregation class?
    field: str
    function: str
    name: Optional[str] = None


class AxisSpec(BaseModel):
    """Form for an axis specification."""

    # TODO: can probably merge wth Axis class?
    field: str
    interval: Optional[str] = None


@app_query.post("/{index}/aggregate")
def query_aggregate_post(
    index: str,
    axes: Optional[List[AxisSpec]] = Body(
        None, description="Axes to aggregate on (i.e. group by)"
    ),
    aggregations: Optional[List[AggregationSpec]] = Body(
        None, description="Aggregate functions to compute"
    ),
    queries: Optional[Union[str, List[str], Dict[str, str]]] = Body(
        None,
        description="Query/Queries to run. Value should be a single query string, a list of query strings, "
        "or a dict of queries {'label': 'query'}",
    ),
    filters: Optional[
        Dict[str, Union[FilterValue, List[FilterValue], FilterSpec]]
    ] = Body(
        None,
        description="Field filters, should be a dict of field names to filter specifications,"
        "which can be either a value, a list of values, or a FilterSpec dict",
    ),
    _user=Depends(authenticated_user),
):
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
    indices = index.split(",")
    _axes = [Axis(**x.model_dump()) for x in axes] if axes else []
    _aggregations = (
        [Aggregation(**x.model_dump()) for x in aggregations] if aggregations else []
    )
    if not (_axes or _aggregations):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aggregation needs at least one axis or aggregation",
        )
    queries = _process_queries(queries)
    filters = dict(_process_filters(filters))
    results = aggregate.query_aggregate(
        indices, _axes, _aggregations, queries=queries, filters=filters
    )
    return {
        "meta": {
            "axes": [axis.asdict() for axis in results.axes],
            "aggregations": [a.asdict() for a in results.aggregations],
        },
        "data": list(results.as_dicts()),
    }


@app_query.post(
    "/{index}/tags_update",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def query_update_tags(
    index: str,
    action: Literal["add", "remove"] = Body(
        None, description="Action (add or remove) on tags"
    ),
    field: str = Body(None, description="Tag field to update"),
    tag: str = Body(None, description="Tag to add or remove"),
    queries: Optional[Union[str, List[str], Dict[str, str]]] = Body(
        None,
        description="Query/Queries to run. Value should be a single query string, a list of query strings, "
        "or a dict of {'label': 'query'}",
    ),
    filters: Optional[
        Dict[str, Union[FilterValue, List[FilterValue], FilterSpec]]
    ] = Body(
        None,
        description="Field filters, should be a dict of field names to filter specifications,"
        "which can be either a value, a list of values, or a FilterSpec dict",
    ),
    ids: Optional[Union[str, List[str]]] = Body(
        None, description="Document IDs of documents to update"
    ),
    _user=Depends(authenticated_user),
):
    """
    Add or remove tags by query or by id
    """
    indices = index.split(",")
    queries = _process_queries(queries)
    filters = dict(_process_filters(filters))
    if isinstance(ids, (str, int)):
        ids = [ids]
    update_tag_query(indices, action, field, tag, queries, filters, ids)
    return
