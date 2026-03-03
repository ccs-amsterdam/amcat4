"""API Endpoints for querying and manipulating documents in an index."""

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field

from amcat4.api.auth_helpers import authenticated_user
from amcat4.models import FieldSpec, FilterSpec, FilterValue, IndexIds, Roles, SortSpec, User
from amcat4.projects.aggregate import Aggregation, Axis, TopHitsAggregation, query_aggregate
from amcat4.projects.query import delete_query, query_documents, update_query, update_tag_query
from amcat4.systemdata.fields import HTTPException_if_invalid_field_access, allowed_fieldspecs
from amcat4.systemdata.roles import HTTPException_if_not_project_index_role

app_index_query = APIRouter(prefix="/index", tags=["query"])


# TYPES
FieldsType = Annotated[
    list[str | FieldSpec] | None,
    Field(
        None,
        description=(
            "Select which document fields to retrieve. Can be a list of field names"
            "or a list of FieldSpec dictionaries. The latter allows specifying snippet lengths."
        ),
        examples=[
            ["title", "body"],
            [{"name": "body", "snippet_length": {"nomatch_chars": 100, "max_matches": 3, "match_chars": 50}}],
        ],
    ),
]

FiltersType = Annotated[
    dict[str, FilterValue | list[FilterValue] | FilterSpec] | None,
    Field(
        None,
        description=(
            "Filter results by field values. Provide a dictionary where keys are field names. "
            "The value can be a list of values for exact matches. For more complex filters, value "
            "can be a FilterSpec dictionary, with keys: 'values', 'gt', 'gte', 'lt', 'lte', 'exists'."
        ),
        examples=[
            {"status": ["published"]},
            {"category": ["news", "blog"]},
            {"date": {"gte": "2023-01-01", "lte": "2023-12-31"}},
        ],
    ),
]

SortType = Annotated[
    str | list[str] | list[dict[str, SortSpec]] | None,
    Field(
        None,
        description=(
            "Sort results by a field. Can be a single field name, a list of field names, "
            "or a list of dictionaries specifying field and sort order."
        ),
        examples=[
            "date",
            ["date", "title"],
            [{"date": {"order": "desc"}}, {"title": {"order": "asc"}}],
        ],
    ),
]

QueriesType = Annotated[
    str | list[str] | dict[str, str] | None,
    Field(
        None,
        description=(
            "Full-text search. Can be a single query string, a list of query strings, "
            "or a dictionary mapping labels to query strings."
        ),
        examples=[
            "this OR that",
            ["this OR that", '"this exactly"'],
            {"My Query": "this OR that"},
        ],
    ),
]


# REQUEST MODELS
class QueryDocumentsBody(BaseModel):
    """Body for querying documents."""

    queries: QueriesType
    fields: FieldsType
    filters: FiltersType
    sort: SortType
    per_page: int = Field(default=10, le=200, description="Number of documents per page.")
    page: int = Field(default=0, description="Which page to retrieve.")
    scroll: str | None = Field(
        None,
        description=(
            "Scroll is the most efficient way to retrieve large result sets. Specify "
            "how long the scroll context should be kept alive, e.g., '5m' for one minute. "
            "results will then contain a scroll_id that can be used to retrieve the next batch."
        ),
    )
    scroll_id: str | None = Field(
        default=None, description="Scroll ID as returned by a previous query for getting the next batch."
    )
    highlight: bool = Field(default=False, description="If true, highlight fields.")


class AggregationSpec(BaseModel):
    """Form for an aggregation."""

    field: str
    function: str
    name: Optional[str] = None

    def instantiate(self):
        return Aggregation(**self.model_dump())


class TopHitsAggregationSpec(BaseModel):
    """Form for a top hits aggregation."""

    fields: list[str]
    function: Literal["top_hits"] = "top_hits"
    name: Optional[str] = None
    sort: Optional[list[dict[str, SortSpec]]] = None
    n: int = 1

    def instantiate(self):
        return TopHitsAggregation(**self.model_dump())


class AxisSpec(BaseModel):
    """Form for an axis specification."""

    field: str
    interval: Optional[str] = None


class QueryAggregateBody(BaseModel):
    """Body for aggregating documents."""

    axes: Optional[List[AxisSpec]] = Field(None, description="Axes to aggregate on.")
    aggregations: Optional[List[AggregationSpec | TopHitsAggregationSpec]] = Field(None, description="Aggregate functions.")
    queries: QueriesType
    filters: FiltersType
    after: Optional[dict[str, Any]] = Field(None, description="After cursor for pagination.")


class UpdateTagsBody(BaseModel):
    """Body for updating tags."""

    action: Literal["add", "remove"] = Field(..., description="Action to perform on tags.")
    field: str = Field(..., description="Tag field to update.")
    tag: str = Field(..., description="Tag to add or remove.")
    queries: QueriesType
    filters: FiltersType
    ids: Optional[Union[str, List[str]]] = Field(None, description="Document IDs to update.")


class UpdateByQueryBody(BaseModel):
    """Body for updating documents by query."""

    field: str = Field(..., description="Field to update.")
    value: str | int | float | None = Field(..., description="New value for the field.")
    queries: QueriesType
    filters: FiltersType
    ids: Optional[List[str]] = Field(None, description="Document IDs to update.")


class DeleteByQueryBody(BaseModel):
    """Body for deleting documents by query."""

    queries: QueriesType
    filters: FiltersType
    ids: Optional[List[str]] = Field(None, description="Document IDs to delete.")


# RESPONSE MODELS
class QueryMeta(BaseModel):
    """Metadata for a query result."""

    total_count: int
    per_page: Optional[int] = None
    page_count: Optional[int] = None
    page: Optional[int] = None
    scroll_id: Optional[str] = None


class QueryResultDict(BaseModel):
    """Results of a document query."""

    results: List[Dict[str, Any]]
    meta: QueryMeta


class AggregateResult(BaseModel):
    """Results of an aggregation query."""

    meta: dict
    data: list[dict]


class QueryUpdateResponse(BaseModel):
    """Response for a tags update operation."""

    updated: int
    total: int


class TaskResponse(BaseModel):
    """Response for a background task."""

    task_id: str = Field(..., description="The ID of the background task.")


@app_index_query.post("/{index}/query")
async def query_documents_post(
    index: IndexIds,
    body: Annotated[QueryDocumentsBody, Body(...)],
    user: User = Depends(authenticated_user),
) -> QueryResultDict:
    """
    Query documents in one or more indices. Requires READER or METAREADER role on the index/indices.
    """
    # TODO: break up the query and scroll logic. So when scroll_id is given, we don't need to check fields/roles again.
    # that DOES require a strict max time window for scrolls though (which we need anyway).
    indices = index.split(",")

    fieldspecs = _standardize_fieldspecs(body.fields)
    if fieldspecs:
        await HTTPException_if_invalid_field_access(indices, user, fieldspecs)
    else:
        fieldspecs = await allowed_fieldspecs(user, indices)

    r = await query_documents(
        indices,
        queries=_standardize_queries(body.queries),
        filters=_standardize_filters(body.filters),
        fields=fieldspecs,
        sort=_standardize_sort(body.sort),
        per_page=body.per_page,
        page=body.page,
        scroll_id=body.scroll_id,
        scroll=body.scroll,
        highlight=body.highlight,
    )
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No results")
    return QueryResultDict(**r.as_dict())


@app_index_query.post("/{index}/aggregate", response_model=AggregateResult)
async def query_aggregate_post(
    index: IndexIds,
    body: Annotated[QueryAggregateBody, Body(...)],
    user: User = Depends(authenticated_user),
):
    """
    Perform an aggregation query on one or more indices. Requires READER or METAREADER role.
    """
    indices = index.split(",")
    fields_to_check = []

    if body.axes:
        for axis in body.axes:
            if axis.field != "_query":
                fields_to_check.append(FieldSpec(name=axis.field))

    if body.aggregations:
        for agg in body.aggregations:
            if isinstance(agg, AggregationSpec):
                fields_to_check.append(FieldSpec(name=agg.field))
            else:
                fields_to_check += [FieldSpec(name=f) for f in agg.fields]

    if fields_to_check:
        await HTTPException_if_invalid_field_access(indices, user, fields_to_check)

    _axes = [Axis(**x.model_dump()) for x in body.axes] if body.axes else []
    _aggregations = [a.instantiate() for a in body.aggregations] if body.aggregations else []
    results = await query_aggregate(
        indices,
        _axes,
        _aggregations,
        queries=_standardize_queries(body.queries),
        filters=_standardize_filters(body.filters),
        after=body.after,
    )

    return {
        "meta": {
            "axes": [axis.asdict() for axis in results.axes],
            "aggregations": [a.asdict() for a in results.aggregations],
            "after": results.after,
        },
        "data": list(results.as_dicts()),
    }


@app_index_query.post("/{index}/tags_update")
async def query_update_tags(
    index: IndexIds,
    body: Annotated[UpdateTagsBody, Body(...)],
    user: User = Depends(authenticated_user),
) -> QueryUpdateResponse:
    """
    Add or remove tags from documents by query or by id. Requires WRITER role on the index/indices.
    """
    indices = index.split(",")
    for i in indices:
        await HTTPException_if_not_project_index_role(user, i, Roles.WRITER)

    ids = body.ids
    if isinstance(ids, (str, int)):
        ids = [ids]
    response = await update_tag_query(
        indices, body.action, body.field, body.tag, _standardize_queries(body.queries), _standardize_filters(body.filters), ids
    )
    return QueryUpdateResponse(**response)


@app_index_query.post("/{index}/update_by_query")
async def update_by_query(
    index: IndexIds,
    body: Annotated[UpdateByQueryBody, Body(...)],
    user: User = Depends(authenticated_user),
) -> QueryUpdateResponse:
    """
    Update documents by query. Requires WRITER role on the index/indices.
    """
    indices = index.split(",")
    for ix in indices:
        await HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)

    response = await update_query(
        indices, body.field, body.value, _standardize_queries(body.queries), _standardize_filters(body.filters), body.ids
    )
    return QueryUpdateResponse(**response)


@app_index_query.post("/{index}/delete_by_query")
async def delete_by_query(
    index: IndexIds,
    body: Annotated[DeleteByQueryBody, Body(...)],
    user: User = Depends(authenticated_user),
) -> QueryUpdateResponse:
    """
    Delete documents by query. Requires WRITER role on the index/indices.
    """
    indices = index.split(",")
    for ix in indices:
        await HTTPException_if_not_project_index_role(user, ix, Roles.WRITER)
    response = await delete_query(indices, _standardize_queries(body.queries), _standardize_filters(body.filters), body.ids)
    return QueryUpdateResponse.model_validate(response)


def _standardize_queries(queries: QueriesType) -> dict[str, str] | None:
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


def _standardize_filters(filters: FiltersType) -> dict[str, FilterSpec] | None:
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


def _standardize_fieldspecs(fields: FieldsType) -> list[FieldSpec] | None:
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
