"""Nested user-document Mongo layout for codebase search."""
from __future__ import annotations

import pytest
from rank_bm25 import BM25Okapi

from src.adapters import codebase_mongo
from src.server.settings import settings


@pytest.fixture(autouse=True)
def reset_client():
    codebase_mongo._client = None
    yield
    codebase_mongo._client = None


class FakeAggCursor:
    def __init__(self, docs: list):
        self._docs = docs
        self._i = 0

    def __aiter__(self):
        self._i = 0
        return self

    async def __anext__(self):
        if self._i >= len(self._docs):
            raise StopAsyncIteration
        d = self._docs[self._i]
        self._i += 1
        return d


class FakeCollectionNested:
    def __init__(self, agg_rows: list):
        self.agg_rows = agg_rows
        self.pipelines: list = []

    def aggregate(self, pipeline, **kwargs):
        self.pipelines.append(pipeline)
        return FakeAggCursor(self.agg_rows)

    def find(self, *args, **kwargs):
        raise AssertionError("nested layout must use aggregate, not find")


class FakeDB:
    def __init__(self, coll):
        self._coll = coll

    def __getitem__(self, name: str):
        return self._coll


class FakeClient:
    def __init__(self, coll):
        self._coll = coll

    def __getitem__(self, name: str):
        return FakeDB(self._coll)


def test_validate_project_id_rejects_bad_chars():
    with pytest.raises(ValueError, match="project_id"):
        codebase_mongo.validate_project_id("project/1")


@pytest.mark.asyncio
async def test_nested_requires_project_id():
    prev = settings.CODEBASE_MONGO_LAYOUT
    settings.CODEBASE_MONGO_LAYOUT = "nested_user_doc"
    try:
        with pytest.raises(ValueError, match="project_id"):
            await codebase_mongo.search_chunks(1, "hello", 10, project_id=None)
    finally:
        settings.CODEBASE_MONGO_LAYOUT = prev


@pytest.mark.asyncio
async def test_nested_uses_aggregate_and_bm25_order():
    """Simulate aggregation rows; BM25 ranks by term frequency in _raw."""
    pad = " z" * 15
    agg_rows = [
        {
            "_path": "low.py",
            "_raw": "token " + pad,
            "_parent_id": "p1",
            "_codebase_ix": 0,
        },
        {
            "_path": "high.py",
            "_raw": "token token token " + pad,
            "_parent_id": "p1",
            "_codebase_ix": 1,
        },
    ]
    fc = FakeCollectionNested(agg_rows)
    prev_uri = settings.CODEBASE_MONGO_URI
    prev_layout = settings.CODEBASE_MONGO_LAYOUT
    settings.CODEBASE_MONGO_URI = "mongodb://localhost:27017"
    settings.CODEBASE_MONGO_LAYOUT = "nested_user_doc"
    try:
        codebase_mongo._client = FakeClient(fc)
        out = await codebase_mongo.search_chunks(1, "token", 5, project_id="project_1")
    finally:
        settings.CODEBASE_MONGO_URI = prev_uri
        settings.CODEBASE_MONGO_LAYOUT = prev_layout
        codebase_mongo._client = None

    assert len(fc.pipelines) == 1
    pipe = fc.pipelines[0]
    assert any("$getField" in str(stage) for stage in pipe)
    tokenized = [codebase_mongo.tokenize(r["_raw"]) for r in agg_rows]
    bm25 = BM25Okapi(tokenized)
    raw_scores = bm25.get_scores(codebase_mongo.tokenize("token"))
    expected = sorted(range(len(agg_rows)), key=lambda i: float(raw_scores[i]), reverse=True)
    assert [out[i]["path"] for i in range(len(out))] == [agg_rows[j]["_path"] for j in expected]
    scores = [r["bm25_score"] for r in out]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_nested_aggregate_limit_matches_bm25_cap():
    agg_rows = []
    fc = FakeCollectionNested(agg_rows)
    prev_uri = settings.CODEBASE_MONGO_URI
    prev_layout = settings.CODEBASE_MONGO_LAYOUT
    prev_cap = settings.CODEBASE_MONGO_BM25_MAX_CANDIDATES
    settings.CODEBASE_MONGO_URI = "mongodb://localhost:27017"
    settings.CODEBASE_MONGO_LAYOUT = "nested_user_doc"
    settings.CODEBASE_MONGO_BM25_MAX_CANDIDATES = 7
    try:
        codebase_mongo._client = FakeClient(fc)
        await codebase_mongo.search_chunks(1, "x", 10, project_id="p1")
    finally:
        settings.CODEBASE_MONGO_URI = prev_uri
        settings.CODEBASE_MONGO_LAYOUT = prev_layout
        settings.CODEBASE_MONGO_BM25_MAX_CANDIDATES = prev_cap
        codebase_mongo._client = None

    lim_stages = [s for s in fc.pipelines[0] if "$limit" in s]
    assert lim_stages and lim_stages[-1]["$limit"] == 7
