from typing import List
from amcat4.models import FieldSpec
from amcat4.projects.query import query_documents


def test_pagination(index_many):
    x = query_documents(index_many, per_page=6)
    assert x is not None
    assert x.page_count == 4
    assert x.per_page == 6
    assert len(x.data) == 6
    assert x.page == 0
    x = query_documents(index_many, per_page=6, page=3)
    assert x is not None
    assert x.page_count == 4
    assert x.per_page == 6
    assert len(x.data) == 20 - 3 * 6
    assert x.page == 3


def test_sort(index_many):
    def q(key, per_page=5) -> List[int]:
        for i, k in enumerate(key):
            if isinstance(k, str):
                key[i] = {k: {"order": "asc"}}
        res = query_documents(index_many, per_page=per_page, fields=[FieldSpec(name="id")], sort=key)
        assert res is not None

        print(list(res.data))
        return [int(h["id"]) for h in res.data]

    assert q(["id"]) == [0, 1, 2, 3, 4]
    assert q(["pagenr"]) == [10, 9, 11, 8, 12]
    assert q(["pagenr", "id"]) == [10, 9, 11, 8, 12]
    assert q([{"pagenr": {"order": "desc"}}, "id"]) == [0, 1, 19, 2, 18]


def test_scroll(index_many):
    r = query_documents(index_many, queries={"odd": "odd"}, scroll="5m", per_page=4, fields=[FieldSpec(name="id")])
    assert r is not None
    assert len(r.data) == 4
    assert r.total_count, 10
    assert r.page_count == 3
    allids = list(r.data)

    r = query_documents(index_many, scroll_id=r.scroll_id, fields=[FieldSpec(name="id")])
    assert r is not None
    assert len(r.data) == 4
    allids += r.data

    r = query_documents(index_many, scroll_id=r.scroll_id, fields=[FieldSpec(name="id")])
    assert r is not None
    assert len(r.data) == 2
    allids += r.data

    r = query_documents(index_many, scroll_id=r.scroll_id, fields=[FieldSpec(name="id")])
    assert r is None

    assert {int(h["id"]) for h in allids} == {0, 2, 4, 6, 8, 10, 12, 14, 16, 18}
