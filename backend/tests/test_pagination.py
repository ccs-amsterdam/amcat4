from typing import List

import pytest

from amcat4.models import FieldSpec
from amcat4.projects.query import query_documents


@pytest.mark.anyio
async def test_pagination(index_many):
    x = await query_documents(index_many, per_page=6)
    assert x is not None
    assert x.page_count == 4
    assert x.per_page == 6
    assert len(x.data) == 6
    assert x.page == 0
    x = await query_documents(index_many, per_page=6, page=3)
    assert x is not None
    assert x.page_count == 4
    assert x.per_page == 6
    assert len(x.data) == 20 - 3 * 6
    assert x.page == 3


@pytest.mark.anyio
async def test_sort(index_many):
    async def q(key, per_page=5) -> List[int]:
        for i, k in enumerate(key):
            if isinstance(k, str):
                key[i] = {k: {"order": "asc"}}
        res = await query_documents(index_many, per_page=per_page, fields=[FieldSpec(name="id")], sort=key)
        assert res is not None

        return [int(h["id"]) for h in res.data]

    assert await q(["id"]) == [0, 1, 2, 3, 4]
    assert await q(["pagenr"]) == [10, 9, 11, 8, 12]
    assert await q(["pagenr", "id"]) == [10, 9, 11, 8, 12]
    assert await q([{"pagenr": {"order": "desc"}}, "id"]) == [0, 1, 19, 2, 18]


@pytest.mark.anyio
async def test_cursor(index_many):
    fields = [FieldSpec(name="id")]
    for queries in [None, {"odd": "odd"}]:
        r = await query_documents(index_many, queries=queries, per_page=4, fields=fields)
        allids = list(r.data)
        while r.next:
            r = await query_documents(index_many, queries=queries, per_page=4, fields=fields, after=r.next)
            allids += r.data
        expected = {0, 2, 4, 6, 8, 10, 12, 14, 16, 18} if queries else set(range(20))
        assert sorted(int(h["id"]) for h in allids) == sorted(expected)
