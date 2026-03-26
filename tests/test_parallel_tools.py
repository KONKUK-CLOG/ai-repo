"""Verify multiple tools in one LLM plan execute concurrently (asyncio.gather)."""
import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from src.server.schemas import LLMExecuteRequest, LLMFinalArtifact
from src.server.routers import agent


@pytest.mark.asyncio
async def test_parallel_tool_execution_timing():
    """Two 80ms tools should finish in ~80ms parallel, not ~160ms sequential."""
    call_delay = 0.08

    async def slow_execute(tool_name: str, params: dict, user_api_key=None):
        await asyncio.sleep(call_delay)
        return {"tool": tool_name, "ok": True}

    plans = [
        {"tool": "get_user_blog_posts", "params": {"limit": 1}},
        {"tool": "search_codebase", "params": {"query": "foo"}},
    ]

    with patch.object(agent, "call_llm_with_tools", new_callable=AsyncMock) as mock_plan:
        mock_plan.return_value = ("thought", plans)
        with patch.object(agent, "_execute_regular_tool", side_effect=slow_execute):
            with patch.object(agent, "_generate_final_response", new_callable=AsyncMock) as mock_final:
                mock_final.return_value = LLMFinalArtifact(
                    answer="a", blog_markdown="# x\n\ny"
                )
                req = LLMExecuteRequest(user_id=1, prompt="both", context={})
                t0 = time.monotonic()
                result = await agent.run_llm_execute_pipeline(req)
                elapsed = time.monotonic() - t0

    assert len(result.tool_calls) == 2
    assert all(tc.success for tc in result.tool_calls)
    # parallel: upper bound a bit above single sleep; sequential would be ~2*call_delay
    assert elapsed < call_delay * 1.35, f"expected parallel ~{call_delay}s, got {elapsed}s"


@pytest.mark.asyncio
async def test_tool_results_order_matches_plan():
    async def execute_in_order(tool_name: str, params: dict, user_api_key=None):
        return {"n": tool_name}

    plans = [
        {"tool": "search_codebase", "params": {"query": "a"}},
        {"tool": "get_user_blog_posts", "params": {}},
    ]

    with patch.object(agent, "call_llm_with_tools", new_callable=AsyncMock) as mock_plan:
        mock_plan.return_value = ("t", plans)
        with patch.object(agent, "_execute_regular_tool", side_effect=execute_in_order):
            with patch.object(agent, "_generate_final_response", new_callable=AsyncMock) as mock_final:
                mock_final.return_value = LLMFinalArtifact(
                    answer="x", blog_markdown="# m\n\nx"
                )
                result = await agent.run_llm_execute_pipeline(
                    LLMExecuteRequest(user_id=7, prompt="p", context={})
                )

    assert [tc.tool for tc in result.tool_calls] == ["search_codebase", "get_user_blog_posts"]
    assert result.tool_calls[0].result == {"n": "search_codebase"}
