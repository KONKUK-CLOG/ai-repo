"""BM25 ranking and Mongo fetch behavior for codebase_mongo."""
from __future__ import annotations

from rank_bm25 import BM25Okapi

import pytest

from src.adapters import codebase_mongo
from src.server.settings import settings


@pytest.fixture(autouse=True)
def reset_mongo_client():
    prev_layout = settings.CODEBASE_MONGO_LAYOUT
    settings.CODEBASE_MONGO_LAYOUT = "flat"
    codebase_mongo._client = None
    yield
    settings.CODEBASE_MONGO_LAYOUT = prev_layout
    codebase_mongo._client = None


class FakeCursor:
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


class FakeCollection:
    def __init__(self, all_docs: list):
        self.all_docs = all_docs
        self.last_find_limit: list[int | None] = []

    def find(self, filt, projection=None, limit=None):
        self.last_find_limit.append(limit)
        lim = limit if limit is not None else len(self.all_docs)
        return FakeCursor(self.all_docs[:lim])


class FakeDB:
    def __init__(self, coll: FakeCollection):
        self._coll = coll

    def __getitem__(self, name: str):
        return self._coll


class FakeClient:
    def __init__(self, coll: FakeCollection):
        self._coll = coll

    def __getitem__(self, name: str):
        return FakeDB(self._coll)


def test_tokenize_splits_whitespace():
    assert codebase_mongo.tokenize("Foo  BAR") == ["foo", "bar"]
    assert codebase_mongo.tokenize("") == []


@pytest.mark.asyncio
async def test_search_chunks_bm25_orders_by_term_frequency():
    """Equal-length docs: more ``auth`` tokens → higher BM25 for query ``auth``."""
    pad = " z" * 20  # shared tail so doc lengths match
    docs = [
        {"_id": 1, "path": "b.py", "content": "auth " + pad},
        {"_id": 2, "path": "a.py", "content": "auth auth auth " + pad},
        {"_id": 3, "path": "c.py", "content": "auth auth " + pad},
    ]
    fc = FakeCollection(docs)

    prev_uri = settings.CODEBASE_MONGO_URI
    prev_max = settings.CODEBASE_MONGO_BM25_MAX_CANDIDATES
    settings.CODEBASE_MONGO_URI = "mongodb://localhost:27017"
    settings.CODEBASE_MONGO_BM25_MAX_CANDIDATES = 500
    try:
        codebase_mongo._client = FakeClient(fc)
        out = await codebase_mongo.search_chunks(1, "auth", top_k=3)
    finally:
        settings.CODEBASE_MONGO_URI = prev_uri
        settings.CODEBASE_MONGO_BM25_MAX_CANDIDATES = prev_max
        codebase_mongo._client = None

    tokenized = [codebase_mongo.tokenize(d["content"]) for d in docs]
    bm25 = BM25Okapi(tokenized)
    raw_scores = bm25.get_scores(codebase_mongo.tokenize("auth"))
    expected = sorted(range(len(docs)), key=lambda i: float(raw_scores[i]), reverse=True)
    expected_paths = [docs[i]["path"] for i in expected]

    assert [o["path"] for o in out] == expected_paths
    scores = [o["bm25_score"] for o in out]
    assert scores == sorted(scores, reverse=True)
    assert len(out) == 3


@pytest.mark.asyncio
async def test_search_chunks_top_k_truncates():
    pad = " z" * 20
    docs = [
        {"_id": 1, "path": "a.py", "content": "auth auth auth " + pad},
        {"_id": 2, "path": "b.py", "content": "auth auth " + pad},
        {"_id": 3, "path": "c.py", "content": "auth " + pad},
    ]
    fc = FakeCollection(docs)
    prev_uri = settings.CODEBASE_MONGO_URI
    prev_max = settings.CODEBASE_MONGO_BM25_MAX_CANDIDATES
    settings.CODEBASE_MONGO_URI = "mongodb://localhost:27017"
    settings.CODEBASE_MONGO_BM25_MAX_CANDIDATES = 500
    try:
        codebase_mongo._client = FakeClient(fc)
        out = await codebase_mongo.search_chunks(1, "auth", top_k=1)
    finally:
        settings.CODEBASE_MONGO_URI = prev_uri
        settings.CODEBASE_MONGO_BM25_MAX_CANDIDATES = prev_max
        codebase_mongo._client = None

    assert len(out) == 1
    tokenized = [codebase_mongo.tokenize(d["content"]) for d in docs]
    bm25 = BM25Okapi(tokenized)
    raw_scores = bm25.get_scores(codebase_mongo.tokenize("auth"))
    best_i = max(range(len(docs)), key=lambda i: float(raw_scores[i]))
    assert out[0]["path"] == docs[best_i]["path"]


@pytest.mark.asyncio
async def test_search_chunks_respects_bm25_max_candidates():
    """Mongo find limit equals CODEBASE_MONGO_BM25_MAX_CANDIDATES."""
    docs = [{"_id": i, "path": f"f{i}.py", "content": "auth token"} for i in range(10)]
    fc = FakeCollection(docs)
    prev_uri = settings.CODEBASE_MONGO_URI
    prev_max = settings.CODEBASE_MONGO_BM25_MAX_CANDIDATES
    settings.CODEBASE_MONGO_URI = "mongodb://localhost:27017"
    settings.CODEBASE_MONGO_BM25_MAX_CANDIDATES = 3
    try:
        codebase_mongo._client = FakeClient(fc)
        out = await codebase_mongo.search_chunks(1, "auth", top_k=10)
    finally:
        settings.CODEBASE_MONGO_URI = prev_uri
        settings.CODEBASE_MONGO_BM25_MAX_CANDIDATES = prev_max
        codebase_mongo._client = None

    assert fc.last_find_limit == [3]
    assert len(out) <= 3
