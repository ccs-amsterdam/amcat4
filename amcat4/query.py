"""
All things query
"""
from math import ceil

from typing import (
    Mapping,
    Iterable,
    Optional,
    Union,
    Sequence,
    Any,
    Dict,
    List,
    Tuple,
    Literal,
)

from .date_mappings import mappings
from .elastic import es, update_tag_by_query
from amcat4 import elastic
from amcat4.util import parse_field
from amcat4.index import Role, get_role


def build_body(
    queries: Iterable[str] = None,
    filters: Mapping = None,
    highlight: dict = None,
    ids: Iterable[str] = None,
):
    def parse_filter(field, filter) -> Tuple[Mapping, Mapping]:
        filter = filter.copy()
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
                field_filters.append(
                    {"bool": {"must_not": {"exists": {"field": field}}}}
                )
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

    def parse_queries(qs: Sequence[str]) -> dict:
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
    if queries:
        if isinstance(queries, dict):
            queries = queries.values()
        fs.append(parse_queries(list(queries)))
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
        data: List[dict],
        n: int = None,
        per_page: int = None,
        page: int = None,
        page_count: int = None,
        scroll_id: str = None,
    ):
        if n and (page_count is None) and (per_page is not None):
            page_count = ceil(n / per_page)
        self.data = data
        self.total_count = n
        self.page = page
        self.page_count = page_count
        self.per_page = per_page
        self.scroll_id = scroll_id

    def as_dict(self):
        meta = {
            "total_count": self.total_count,
            "per_page": self.per_page,
            "page_count": self.page_count,
        }
        if self.scroll_id:
            meta["scroll_id"] = self.scroll_id
        else:
            meta["page"] = self.page
        return dict(meta=meta, results=self.data)


def _normalize_queries(
    queries: Optional[Union[Dict[str, str], Iterable[str]]]
) -> Mapping[str, str]:
    if queries is None:
        return {}
    if isinstance(queries, dict):
        return queries
    return {q: q for q in queries}


def query_documents(
    index: Union[str, Sequence[str]],
    queries: Union[Mapping[str, str], Iterable[str]] = None,
    *,
    page: int = 0,
    per_page: int = 10,
    scroll=None,
    scroll_id: str = None,
    fields: Iterable[str] = None,
    snippets: Iterable[str] = None,
    filters: Mapping[str, Mapping] = None,
    highlight: Literal["none", "text", "snippets"] = "none",
    sort: List[Union[str, Mapping]] = None,
    **kwargs,
) -> Optional[QueryResult]:
    """
    Conduct a query_string query, returning the found documents.

    It will return at most per_page results.
    In normal (paginated) mode, the next batch can be  requested by incrementing the page parameter.
    If the scroll parameter is given, the result will contain a scroll_id which can be used to get the next batch.
    In case there are no more documents to scroll, it will return None
    :param index: The name of the index or indexes
    :param queries: a list of queries OR a dict {label1: query1, ...}
    :param page: The number of the page to request (starting from zero)
    :param per_page: The number of hits per page
    :param scroll: if not None, will create a scroll request rather than a paginated request. Parmeter should
                   specify the time the context should be kept alive, or True to get the default of 2m.
    :param scroll_id: if not None, should be a previously returned context_id to retrieve a new page of results
    :param fields: if not None, specify a list of fields to retrieve for each hit
    :param filters: if not None, a dict of filters with either value, values, or gte/gt/lte/lt ranges:
                       {field: {'values': [value1,value2],
                                'value': value,
                                'gte/gt/lte/lt': value,
                                ...}}
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
    queries = _normalize_queries(queries)
    if sort is not None:
        kwargs["sort"] = sort
    if scroll_id:
        result = es().scroll(scroll_id=scroll_id, **kwargs)
        if not result["hits"]["hits"]:
            return None
    else:
        h = query_highlight(fields, highlight)
        body = build_body(queries.values(), filters, h)

        if fields:
            fields = fields if isinstance(fields, list) else list(fields)
            kwargs["_source"] = fields
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
        return QueryResult(
            data, n=result["hits"]["total"]["value"], scroll_id=result["_scroll_id"]
        )
    elif scroll:
        return QueryResult(
            data,
            n=result["hits"]["total"]["value"],
            per_page=per_page,
            scroll_id=result["_scroll_id"],
        )
    else:
        return QueryResult(
            data, n=result["hits"]["total"]["value"], per_page=per_page, page=page
        )


def query_highlight(fields: Iterable[str] = None, highlight_queries: bool = False):
    """
    The elastic "highlight" parameters works for both highlighting text fields and adding snippets.
    This function will return the highlight parameter to be added to the query body.
    """

    highlight = {
        # "pre_tags": ["<em>"] if highlight is True else [""],
        # "post_tags": ["</em>"] if highlight is True else [""],
        "require_field_match": True,
    }

    if fields is None:
        if highlight_queries is True:
            highlight["fields"]["*"] = {"number_of_fragments": 0}
    else:
        highlight["fields"] = {}
        for field in fields:
            fieldname, nomatch_chars, max_matches, match_chars = parse_field(field)
            if nomatch_chars is None:
                if highlight_queries is True:
                    # This will overwrite the field with the highlighted version, so
                    # only needed if highlight is True
                    highlight["fields"][fieldname] = {"number_of_fragments": 0}
            else:
                # the elastic highlight feature is also used to get snippets. note that
                # above in the
                highlight["fields"][fieldname] = {
                    "no_match_size": nomatch_chars,
                    "number_of_fragments": max_matches,
                    "fragment_size": match_chars,
                }
                if highlight_queries is False or max_matches == 0:
                    # This overwrites the actual query, so that the highlights are not returned.
                    # Also used to get the nomatch snippet if max_matches = 0
                    highlight["fields"][fieldname]["highlight_query"] = {
                        "match_all": {}
                    }

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
    index: Union[str, Sequence[str]],
    action: Literal["add", "remove"],
    field: str,
    tag: str,
    queries: Union[Mapping[str, str], Iterable[str]] = None,
    filters: Mapping[str, Mapping] = None,
    ids: Sequence[str] = None,
):
    """Add or remove tags using a query"""
    body = build_body(queries and queries.values(), filters, ids=ids)
    update_tag_by_query(index, action, body, field, tag)
