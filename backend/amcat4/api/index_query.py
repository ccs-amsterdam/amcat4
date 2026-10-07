"""API Endpoints for querying and manipulating documents in an index."""

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from amcat4.api.auth_helpers import authenticated_user
from amcat4.models import FieldSpec, FilterSpec, FilterValue, IndexId, Roles, SortSpec, User
from amcat4.projects.aggregate import MAX_LIMIT, Aggregation, Axis, TopHitsAggregation, query_aggregate
from amcat4.projects.query import delete_query, query_documents, update_query, update_tag_query
from amcat4.systemdata.fields import HTTPException_if_invalid_field_access, field_access
from amcat4.systemdata.roles import HTTPException_if_not_project_index_role

app_index_query = APIRouter(prefix="", tags=["query"])


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
            'or a list of dictionaries specifying field and sort order. Use "?" for random order.'
        ),
        examples=[
            "date",
            "?",
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
class SimilarSpec(BaseModel):
    field: str = Field(description="The vector field")
    vector: list[float] = Field(description="The vector to compare to")


class QueryDocumentsBody(BaseModel):
    """Body for querying documents."""

    queries: QueriesType
    fields: FieldsType
    filters: FiltersType
    sort: SortType
    per_page: int = Field(default=10, le=1000, description="Number of documents per page.")
    page: int = Field(default=0, description="Which page to retrieve.")
    after: str | None = Field(
        default=None,
        description=(
            "Cursor to get the next batch of results: the 'next' value from the meta of the previous result (send the "
            "same query again). This is the efficient way to retrieve large result sets (especially without sort)."
        ),
    )
    highlight: bool = Field(default=False, description="If true, highlight fields.")
    similar: SimilarSpec | None = Field(
        default=None, description="Order results by similarity to this vector (cosine similarity on a vector field)"
    )


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
    order: Literal["axes", "count"] = Field(
        "axes", description="Sort the results by the axis values, or by the number of documents (descending)"
    )
    limit: int = Field(1000, ge=1, le=MAX_LIMIT, description="Maximum number of rows to return")


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
    next: Optional[str] = Field(None, description="Cursor for the next batch of results (use as 'after')")


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


class MultiProjectQueryBody(QueryDocumentsBody):
    projects: list[IndexId] = Field(description="The projects to query")


class MultiProjectAggregateBody(QueryAggregateBody):
    projects: list[IndexId] = Field(description="The projects to query")


async def _query(indices: list[str], body: QueryDocumentsBody, user: User) -> QueryResultDict:
    fieldspecs = _standardize_fieldspecs(body.fields)
    access = await field_access(user, indices)
    if fieldspecs:
        await HTTPException_if_invalid_field_access(indices, user, fieldspecs)
    else:
        fieldspecs = list(access.visible.values())
    similar = None
    if body.similar:
        if body.similar.field not in access.queryable:
            raise HTTPException(403, f"Cannot query field {body.similar.field}")
        similar = (body.similar.field, body.similar.vector)

    r = await query_documents(
        indices,
        queries=_standardize_queries(body.queries),
        filters=_standardize_filters(body.filters),
        fields=fieldspecs,
        sort=_standardize_sort(body.sort),
        per_page=body.per_page,
        page=body.page,
        after=body.after,
        highlight=body.highlight,
        similar=similar,
        queryable=None if user.auth_disabled else access.queryable,
    )
    return QueryResultDict(**r.as_dict())


@app_index_query.post("/index/{index}/query")
async def query_documents_post(
    index: IndexId,
    body: Annotated[QueryDocumentsBody, Body(...)],
    user: User = Depends(authenticated_user),
) -> QueryResultDict:
    """
    Query documents in a project. Requires READER or METAREADER role.
    """
    return await _query([index], body, user)


@app_index_query.post("/query")
async def query_projects_post(
    body: Annotated[MultiProjectQueryBody, Body(...)],
    user: User = Depends(authenticated_user),
) -> QueryResultDict:
    """
    Query documents in one or more projects. Requires READER or METAREADER role on all projects.
    """
    return await _query(body.projects, body, user)


async def _aggregate(indices: list[str], body: QueryAggregateBody, user: User):
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
    access = await field_access(user, indices)
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
        order=body.order,
        limit=body.limit,
        queryable=None if user.auth_disabled else access.queryable,
    )
    return {
        "meta": {
            "axes": [axis.asdict() for axis in results.axes],
            "aggregations": [a.asdict() for a in results.aggregations],
            "truncated": results.truncated,
        },
        "data": list(results.as_dicts()),
    }


@app_index_query.post("/index/{index}/aggregate", response_model=AggregateResult)
async def query_aggregate_post(
    index: IndexId,
    body: Annotated[QueryAggregateBody, Body(...)],
    user: User = Depends(authenticated_user),
):
    """
    Perform an aggregation query on a project. Requires READER or METAREADER role.
    """
    return await _aggregate([index], body, user)


@app_index_query.post("/aggregate", response_model=AggregateResult)
async def aggregate_projects_post(
    body: Annotated[MultiProjectAggregateBody, Body(...)],
    user: User = Depends(authenticated_user),
):
    """
    Perform an aggregation query on one or more projects. Requires READER or METAREADER role on all projects.
    """
    return await _aggregate(body.projects, body, user)


@app_index_query.post("/index/{index}/tags_update")
async def query_update_tags(
    index: IndexId,
    body: Annotated[UpdateTagsBody, Body(...)],
    user: User = Depends(authenticated_user),
) -> QueryUpdateResponse:
    """
    Add or remove tags from documents by query or by id. Requires WRITER role on the project.
    """
    await HTTPException_if_not_project_index_role(user, index, Roles.WRITER)

    ids = body.ids
    if isinstance(ids, (str, int)):
        ids = [ids]
    response = await update_tag_query(
        index, body.action, body.field, body.tag, _standardize_queries(body.queries), _standardize_filters(body.filters), ids
    )
    return QueryUpdateResponse(**response)


@app_index_query.post("/index/{index}/update_by_query")
async def update_by_query(
    index: IndexId,
    body: Annotated[UpdateByQueryBody, Body(...)],
    user: User = Depends(authenticated_user),
) -> QueryUpdateResponse:
    """
    Update documents by query. Requires WRITER role on the project.
    """
    await HTTPException_if_not_project_index_role(user, index, Roles.WRITER)

    response = await update_query(
        index, body.field, body.value, _standardize_queries(body.queries), _standardize_filters(body.filters), body.ids
    )
    return QueryUpdateResponse(**response)


@app_index_query.post("/index/{index}/delete_by_query")
async def delete_by_query(
    index: IndexId,
    body: Annotated[DeleteByQueryBody, Body(...)],
    user: User = Depends(authenticated_user),
) -> QueryUpdateResponse:
    """
    Delete documents by query. Requires WRITER role on the project.
    """
    await HTTPException_if_not_project_index_role(user, index, Roles.WRITER)
    response = await delete_query(index, _standardize_queries(body.queries), _standardize_filters(body.filters), body.ids)
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
