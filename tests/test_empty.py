import pytest


@pytest.mark.anyio
async def test_empty(index):
    assert False
