"""Tests for Mongo codebase search tool and agent registry."""
from unittest.mock import AsyncMock, patch

import pytest

from src.mcp.tools import search_codebase_mongo
from src.server.routers.agent import TOOLS_REGISTRY
from src.server.settings import settings


def test_tools_registry_includes_search_codebase():
    assert "search_codebase" in TOOLS_REGISTRY
    assert TOOLS_REGISTRY["search_codebase"] is search_codebase_mongo


@pytest.mark.asyncio
async def test_search_codebase_run_requires_query():
    out = await search_codebase_mongo.run({"user_id": 1, "query": "  "})
    assert out["success"] is False


@pytest.mark.asyncio
async def test_search_codebase_run_requires_user_id():
    out = await search_codebase_mongo.run({"query": "foo"})
    assert out["success"] is False


@pytest.mark.asyncio
async def test_search_codebase_run_without_mongo_uri():
    prev = settings.CODEBASE_MONGO_URI
    settings.CODEBASE_MONGO_URI = None
    try:
        out = await search_codebase_mongo.run({"user_id": 1, "query": "handler"})
        assert out["success"] is False
        assert "not configured" in out["error"].lower()
    finally:
        settings.CODEBASE_MONGO_URI = prev


@pytest.mark.asyncio
async def test_search_codebase_run_calls_adapter():
    fake = [{"path": "a.py", "content_preview": "x", "content_length": 1, "id": "1"}]
    prev_uri = settings.CODEBASE_MONGO_URI
    settings.CODEBASE_MONGO_URI = "mongodb://localhost:27017"
    try:
        with patch(
            "src.adapters.codebase_mongo.search_chunks",
            new_callable=AsyncMock,
        ) as mock_search:
            mock_search.return_value = fake
            out = await search_codebase_mongo.run(
                {"user_id": 42, "query": "authenticate", "top_k": 5}
            )
    finally:
        settings.CODEBASE_MONGO_URI = prev_uri

    assert out["success"] is True
    assert out["total_results"] == 1
    assert out["results"] == fake
    mock_search.assert_awaited_once_with(42, "authenticate", 5)
