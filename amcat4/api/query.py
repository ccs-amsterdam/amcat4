"""API Endpoints for querying."""

from re import search
from typing import Annotated, Dict, List, Optional, Any, Union, Iterable, Literal

from fastapi import APIRouter, HTTPException, status, Depends, Response, Body
from pydantic import InstanceOf
from pydantic.main import BaseModel

from amcat4 import query, aggregate
from amcat4.aggregate import Axis, Aggregation
from amcat4.api.auth import authenticated_user, check_fields_access
from amcat4.index import Role, get_role, get_fields
from amcat4.models import FieldSpec, FilterSpec, FilterValue, SortSpec
from amcat4.query import update_tag_query

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
    user: str, indices: Iterable[str], fields: list[FieldSpec] | None = None
) -> list[FieldSpec]:
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
        index_fields = get_fields(indices[0])
        role = get_role(indices[0], user)
        allowed_fields: list[FieldSpec] = []
        for field in index_fields.keys():
            if role >= Role.READER:
                allowed_fields.append(FieldSpec(name=field))
            elif role == Role.METAREADER:
                metareader = index_fields[field].metareader
                if metareader.access == "read":
                    allowed_fields.append(FieldSpec(name=field))
                if metareader.access == "snippet":
                    allowed_fields.append(FieldSpec(name=field, snippet=metareader.max_snippet))
            else:
                raise HTTPException(
                    status_code=401,
                    detail=f"User {user} does not have a role on index {indices[0]}",
                )
        return allowed_fields

    for index in indices:
        check_fields_access(index, user, fields)
    return fields


def _standardize_queries(queries: str | list[str] | dict[str, str] | None = None) -> dict[str, str] | None:
    """Convert query json to dict format: {label1:query1, label2: query2} uses indices if no labels given."""

    if queries:
        # to dict format: {label1:query1, label2: query2}  uses indices if no labels given
        if isinstance(queries, str):
            return {"1": queries}
        elif isinstance(queries, list):
            return {str(i): q for i, q in enumerate(queries)}
        elif isinstance(queries, dict):
            return queries
    return None


def _standardize_filters(
    filters: dict[str, FilterValue | list[FilterValue] | FilterSpec] | None = None
) -> dict[str, FilterSpec] | None:
    """Convert filters to dict format: {field: {values: []}}."""
    if not filters:
        return None

    f: dict[str, FilterSpec] = {}
    for field, filter_ in filters.items():
        if isinstance(filter_, str):
            f[field] = FilterSpec(values=[filter_])
        elif isinstance(filter_, list):
            f[field] = FilterSpec(values=filter_)
        elif isinstance(filter_, FilterSpec):
            f[field] = filter_
        else:
            raise ValueError(f"Cannot parse filter: {filter_}")
    return f


def _standardize_fieldspecs(fields: list[str | FieldSpec] | None = None) -> list[FieldSpec] | None:
    """Convert fields to list of FieldSpecs."""
    if not fields:
        return None

    f = []
    for field in fields:
        if isinstance(field, str):
            f.append(FieldSpec(name=field))
        elif isinstance(field, FieldSpec):
            f.append(field)
        else:
            raise ValueError(f"Cannot parse field: {field}")
    return f


def _standardize_sort(sort: str | list[str] | list[dict[str, SortSpec]] | None = None) -> list[dict[str, SortSpec]] | None:
    """Convert sort to list of dicts."""

    # TODO: sort cannot be right. that array around dict is useless

    if not sort:
        return None
    if isinstance(sort, str):
        return [{sort: SortSpec(order="asc")}]

    sortspec: list[dict[str, SortSpec]] = []

    for field in sort:
        if isinstance(field, str):
            sortspec.append({field: SortSpec(order="asc")})
        elif isinstance(field, dict):
            sortspec.append(field)
        else:
            raise ValueError(f"Cannot parse sort: {sort}")

    return sortspec


@app_query.post("/{index}/query", response_model=QueryResult)
def query_documents_post(
    index: str,
    queries: Annotated[
        str | list[str] | dict[str, str] | None,
        Body(
            description="Query/Queries to run. Value should be a single query string, a list of query strings, "
            "or a dict of {'label': 'query'}",
        ),
    ] = None,
    fields: Annotated[
        list[str | FieldSpec] | None,
        Body(
            description="List of fields to retrieve for each document"
            "In the list you can specify a fieldname, but also a FieldSpec dict."
            "Using the FieldSpec allows you to request only a snippet of a field."
            "fieldname[nomatch_chars;max_matches;match_chars]. 'matches' here refers to words from text queries. "
            "If there is no query, the snippet is the first [nomatch_chars] characters. "
            "If there is a query, snippets are returned for up to [max_matches] matches, with each match having [match_chars] "
            "characters. If there are multiple matches, they are concatenated with ' ... '.",
            openapi_examples={
                "simple": {"summary": "Retrieve single field", "value": '["title", "text", "date"]'},
                "text as snippet": {
                    "summary": "Retrieve the full title, but text only as snippet",
                    "value": '["title", {"name": "text", "snippet": {"nomatch_chars": 100}}]',
                },
                "all allowed fields": {
                    "summary": "If fields is left empty, all fields that the user is allowed to see are returned",
                },
            },
        ),
    ] = None,
    filters: Annotated[
        dict[str, FilterValue | list[FilterValue] | FilterSpec] | None,
        Body(
            description="Field filters, should be a dict of field names to filter specifications,"
            "which can be either a value, a list of values, or a FilterSpec dict",
        ),
    ] = None,
    sort: Annotated[
        str | list[str] | list[dict[str, SortSpec]] | None,
        Body(
            description="Sort by field name(s) or dict (see "
            "https://www.elastic.co/guide/en/elasticsearch/reference/current/sort-search-results.html for dict format)",
            openapi_examples={
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
    ] = None,
    per_page: Annotated[int, Body(description="Number of documents per page")] = 10,
    page: Annotated[int, Body(description="Which page to retrieve")] = 0,
    scroll: Annotated[
        str | None,
        Body(
            description="Scroll specification (e.g. '5m') to start a scroll request"
            "This will return a scroll_id which should be passed to subsequent calls"
            "(this is the advised way of scrolling through multiple pages of results)",
            examples=["5m"],
        ),
    ] = None,
    scroll_id: Annotated[str | None, Body(description="Scroll id from previous response to continue scrolling")] = None,
    highlight: Annotated[bool, Body(description="If true, highlight fields")] = False,
    user: str = Depends(authenticated_user),
):
    """
    List or query documents in this index.

    Returns a JSON object {data: [...], meta: {total_count, per_page, page_count, page|scroll_id}}
    """

    indices = index.split(",")
    fieldspecs = get_or_validate_allowed_fields(user, indices, _standardize_fieldspecs(fields))

    r = query.query_documents(
        indices,
        queries=_standardize_queries(queries),
        filters=_standardize_filters(filters),
        fields=fieldspecs,
        sort=_standardize_sort(sort),
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
    axes: Optional[List[AxisSpec]] = Body(None, description="Axes to aggregate on (i.e. group by)"),
    aggregations: Optional[List[AggregationSpec]] = Body(None, description="Aggregate functions to compute"),
    queries: Annotated[
        str | list[str] | dict[str, str] | None,
        Body(
            description="Query/Queries to run. Value should be a single query string, a list of query strings, "
            "or a dict of {'label': 'query'}",
        ),
    ] = None,
    filters: Annotated[
        dict[str, FilterValue | list[FilterValue] | FilterSpec] | None,
        Body(
            description="Field filters, should be a dict of field names to filter specifications,"
            "which can be either a value, a list of values, or a FilterSpec dict",
        ),
    ] = None,
    after: Annotated[dict[str, Any] | None, Body(description="After cursor for pagination")] = None,
    user: str = Depends(authenticated_user),
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
    _aggregations = [Aggregation(**x.model_dump()) for x in aggregations] if aggregations else []
    if not (_axes or _aggregations):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aggregation needs at least one axis or aggregation",
        )

    results = aggregate.query_aggregate(
        indices,
        _axes,
        _aggregations,
        queries=_standardize_queries(queries),
        filters=_standardize_filters(filters),
        after=after,
    )

    return {
        "meta": {
            "axes": [axis.asdict() for axis in results.axes],
            "aggregations": [a.asdict() for a in results.aggregations],
            "after": results.after,
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
    action: Literal["add", "remove"] = Body(None, description="Action (add or remove) on tags"),
    field: str = Body(None, description="Tag field to update"),
    tag: str = Body(None, description="Tag to add or remove"),
    queries: Annotated[
        str | list[str] | dict[str, str] | None,
        Body(
            description="Query/Queries to run. Value should be a single query string, a list of query strings, "
            "or a dict of {'label': 'query'}",
        ),
    ] = None,
    filters: Annotated[
        dict[str, FilterValue | list[FilterValue] | FilterSpec] | None,
        Body(
            description="Field filters, should be a dict of field names to filter specifications,"
            "which can be either a value, a list of values, or a FilterSpec dict",
        ),
    ] = None,
    ids: Optional[Union[str, List[str]]] = Body(None, description="Document IDs of documents to update"),
    user: str = Depends(authenticated_user),
):
    """
    Add or remove tags by query or by id
    """
    indices = index.split(",")

    if isinstance(ids, (str, int)):
        ids = [ids]
    update_tag_query(indices, action, field, tag, _standardize_queries(queries), _standardize_filters(filters), ids)
    return
