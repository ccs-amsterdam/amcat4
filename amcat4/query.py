"""
All things query
"""

from math import ceil

from typing import (
    Union,
    Sequence,
    Any,
    Dict,
    Tuple,
    Literal,
)

from urllib3 import Retry

from amcat4.models import FieldSpec, FilterSpec, SortSpec

from .date_mappings import mappings
from .elastic import es
from amcat4.index import update_documents_by_query, update_tag_by_query


def build_body(
    queries: dict[str, str] | None = None,
    filters: dict[str, FilterSpec] | None = None,
    highlight: dict | None = None,
    ids: list[str] | None = None,
):
    def parse_filter(field: str, filterSpec: FilterSpec) -> Tuple[dict, dict]:
        filter = filterSpec.model_dump(exclude_none=True)
        extra_runtime_mappings = {}
        field_filters = []
        for value in filter.pop("values", []):
            field_filters.append({"term": {field: value}})
        if "value" in filter:
            field_filters.append({"term": {field: filter.pop("value")}})
        if "exists" in filter:
            if filter.pop("exists"):
                field_filters.append({"exists": {"field": field}})
            else:
                field_filters.append({"bool": {"must_not": {"exists": {"field": field}}}})
        for mapping in mappings():
            if mapping.interval in filter:
                value = filter.pop(mapping.interval)
                extra_runtime_mappings.update(mapping.mapping(field))
                field_filters.append({"term": {mapping.fieldname(field): value}})
        rangefilter = {}
        for rangevar in ["gt", "gte", "lt", "lte"]:
            if rangevar in filter:
                rangefilter[rangevar] = filter.pop(rangevar)
        if rangefilter:
            field_filters.append({"range": {field: rangefilter}})
        if filter:
            raise ValueError(f"Unknown filter type(s): {filter}")
        return extra_runtime_mappings, {"bool": {"should": field_filters}}

    def parse_query(q: str) -> dict:
        return {"query_string": {"query": q}}

    def parse_queries(queries: dict[str, str]) -> dict:
        qs = queries.values()
        if len(qs) == 1:
            return parse_query(list(qs)[0])
        else:
            return {"bool": {"should": [parse_query(q) for q in qs]}}

    if not (queries or filters or ids or highlight):
        return {"query": {"match_all": {}}}

    fs, runtime_mappings = [], {}
    if filters:
        for field, filter in filters.items():
            extra_runtime_mappings, filter_term = parse_filter(field, filter)
            fs.append(filter_term)
            if extra_runtime_mappings:
                runtime_mappings.update(extra_runtime_mappings)
    if queries is not None:
        fs.append(parse_queries(queries))
    if ids:
        fs.append({"ids": {"values": list(ids)}})
    body: Dict[str, Any] = {"query": {"bool": {"filter": fs}}}
    if runtime_mappings:
        body["runtime_mappings"] = runtime_mappings

    if highlight is not None:
        body["highlight"] = highlight

    return body


class QueryResult:
    def __init__(
        self,
        data: list[dict],
        n: int | None = None,
        per_page: int | None = None,
        page: int | None = None,
        page_count: int | None = None,
        scroll_id: str | None = None,
    ):
        if n and (page_count is None) and (per_page is not None):
            page_count = ceil(n / per_page)
        self.data = data
        self.total_count = n
        self.page = page
        self.page_count = page_count
        self.per_page = per_page
        self.scroll_id = scroll_id

    def as_dict(self) -> dict:
        meta: dict[str, int | str | None] = {
            "total_count": self.total_count,
            "per_page": self.per_page,
            "page_count": self.page_count,
        }
        if self.scroll_id:
            meta["scroll_id"] = self.scroll_id
        else:
            meta["page"] = self.page
        return dict(meta=meta, results=self.data)


def query_documents(
    index: Union[str, list[str]],
    fields: list[FieldSpec] | None = None,
    queries: dict[str, str] | None = None,
    filters: dict[str, FilterSpec] | None = None,
    sort: list[dict[str, SortSpec]] | None = None,
    *,
    page: int = 0,
    per_page: int = 10,
    scroll=None,
    scroll_id: str | None = None,
    highlight: bool = False,
    **kwargs,
) -> QueryResult | None:
    """
    Conduct a query_string query, returning the found documents.

    It will return at most per_page results.
    In normal (paginated) mode, the next batch can be  requested by incrementing the page parameter.
    If the scroll parameter is given, the result will contain a scroll_id which can be used to get the next batch.
    In case there are no more documents to scroll, it will return None
    :param index: The name of the index or indexes
    :param fields: List of fields using the FieldSpec syntax. If not specified, only return _id.
                   !Any logic for determining whether a user can see the field should be done in the API layer.
    :param queries: if not None, a dict with labels and queries {label1: query1, ...}
    :param filters: if not None, a dict where the key is the field and the value is a FilterSpec

    :param page: The number of the page to request (starting from zero)
    :param per_page: The number of hits per page
    :param scroll: if not None, will create a scroll request rather than a paginated request. Parmeter should
                   specify the time the context should be kept alive, or True to get the default of 2m.
    :param scroll_id: if not None, should be a previously returned context_id to retrieve a new page of results
    :param highlight: if True, add <em> tags to query matches in fields
    :param sort: Sort order of results, can be either a single field or a list of fields.
                 In the list, each field is a string or a dict with options, e.g. ["id", {"date": {"order": "desc"}}]
                 (https://www.elastic.co/guide/en/elasticsearch/reference/current/sort-search-results.html)
    :param kwargs: Additional elements passed to Elasticsearch.search()
    :return: a QueryResult, or None if there is not scroll result anymore
    """
    if fields is not None and not isinstance(fields, list):
        raise ValueError("fields should be a list")

    if scroll or scroll_id:
        # set scroll to default also if scroll_id is given but no scroll time is known
        kwargs["scroll"] = "2m" if (not scroll or scroll is True) else scroll

    if sort is not None:
        kwargs["sort"] = []
        for s in sort:
            for k, v in s.items():
                kwargs["sort"].append({k: dict(v)})

    if scroll_id:
        result = es().scroll(scroll_id=scroll_id, **kwargs)
        if not result["hits"]["hits"]:
            return None
    else:
        h = query_highlight(fields, highlight) if fields is not None else None
        body = build_body(queries, filters, h)

        fieldnames = [field.name for field in fields] if fields is not None else ["_id"]
        kwargs["_source"] = fieldnames

        if not scroll:
            kwargs["from_"] = page * per_page
        result = es().search(index=index, size=per_page, **body, **kwargs)

    data = []
    for hit in result["hits"]["hits"]:
        hitdict = dict(_id=hit["_id"], **hit["_source"])
        hitdict = overwrite_highlight_results(hit, hitdict)
        if "highlight" in hit:
            for key in hit["highlight"].keys():
                if hit["highlight"][key]:
                    hitdict[key] = " ... ".join(hit["highlight"][key])
        data.append(hitdict)
    if scroll_id:
        return QueryResult(data, n=result["hits"]["total"]["value"], scroll_id=result["_scroll_id"])
    elif scroll:
        return QueryResult(
            data,
            n=result["hits"]["total"]["value"],
            per_page=per_page,
            scroll_id=result["_scroll_id"],
        )
    else:
        n = result["hits"]["total"]["value"]
        if n == 10000:
            # Default elastic max on non-scrolled values. I think we should return the actual count,
            # even if elastic will error (I think) if the user ever retrieves a page > 1000
            # TODO: can we not hard-code the 10k limit?
            res = es().count(index=index, query=body["query"])
            n = res["count"]

        return QueryResult(data, n=n, per_page=per_page, page=page)


def query_highlight(fields: list[FieldSpec], highlight_queries: bool = False) -> dict[str, Any]:
    """
    The elastic "highlight" parameters works for both highlighting text fields and adding snippets.
    This function will return the highlight parameter to be added to the query body.
    """

    highlight: dict[str, Any] = {
        "pre_tags": ["<em>"] if highlight_queries is True else [""],
        "post_tags": ["</em>"] if highlight_queries is True else [""],
        "require_field_match": True,
        "fields": {},
    }

    for field in fields:
        if field.snippet is None:
            if highlight_queries is True:
                # This will overwrite the field with the highlighted version, so
                # only needed if highlight is True
                highlight["fields"][field.name] = {"number_of_fragments": 0}
        else:
            # the elastic highlight feature is also used to get snippets. note that
            # above in the
            highlight["fields"][field.name] = {
                "no_match_size": field.snippet.nomatch_chars,
                "number_of_fragments": field.snippet.max_matches,
                "fragment_size": field.snippet.match_chars or 1,  # 0 would return the whole field
            }
            if field.snippet.max_matches == 0:
                # If max_matches is zero, we drop the query for highlighting so that
                # the nomatch_chars are returned
                highlight["fields"][field.name]["highlight_query"] = {"match_all": {}}

    return highlight


def overwrite_highlight_results(hit: dict, hitdict: dict):
    """
    highlights are a separate field in the hits. If highlight is True, we want to overwrite
    the original field with the highlighted version. If there are snippets, we want to add them
    """
    if not hit.get("highlight"):
        return hitdict
    for key in hit["highlight"].keys():
        if hit["highlight"][key]:
            hitdict[key] = " ... ".join(hit["highlight"][key])
    return hitdict


def update_tag_query(
    index: str | list[str],
    action: Literal["add", "remove"],
    field: str,
    tag: str,
    queries: dict[str, str] | None = None,
    filters: dict[str, FilterSpec] | None = None,
    ids: list[str] | None = None,
):
    """Add or remove tags using a query"""
    body = build_body(queries, filters, ids=ids)

    update_result = update_tag_by_query(index, action, body, field, tag)
    return update_result


def update_query(
    index: str | list[str],
    field: str,
    value: Any,
    queries: dict[str, str] | None = None,
    filters: dict[str, FilterSpec] | None = None,
    ids: list[str] | None = None,
):
    query = build_body(queries, filters, ids=ids)
    return update_documents_by_query(index=index, query=query["query"], field=field, value=value)
