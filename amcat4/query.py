"""
All things query
"""
from math import ceil

from .elastic import PREFIX, DOCTYPE, es


class QueryResult:
    def __init__(self, data, n, page, per_page, page_count=None):
        if page_count is None:
            page_count = ceil(n / per_page)
        self.data = data
        self.total_count = n
        self.page = page
        self.page_count = page_count
        self.per_page = per_page

    def as_dict(self):
        return dict(meta=dict(total_count=self.total_count,
                              page=self.page, per_page=self.per_page, page_count=self.page_count),
                    results=self.data)


def query_documents(project_name: str, query_string: str = None, page=1, per_page=10, **kwargs) -> QueryResult:
    """
    Conduct a query_string query, returning the found documents


    :param project_name: The name of the project (without prefix)
    :param query_string: The elasticsearch query_string
    :param page: The number of the page to request (starting from one)
    :param per_page: The number of hits per page
    :param kwargs: Additional elements passed to Elasticsearch.search(), for example:
           sort=col1:desc,col2
    :return: an iterator of article dicts
    """
    index = "".join([PREFIX, project_name])
    if query_string:
        body = dict(query=dict(query_string=dict(default_field="text", query=query_string)))
    else:
        body = dict(query=dict(match_all={}))

    from_ = (page - 1) * per_page
    result = es.search(index, DOCTYPE, body, from_=from_, size=per_page, **kwargs)
    data = [dict(_id=hit['_id'], **hit['_source']) for  hit in result['hits']['hits']]
    return QueryResult(data, n=result['hits']['total'], page=page, per_page=per_page)

