"""Tests for chat history on LLM execute and SSE stream endpoint."""
from unittest.mock import AsyncMock, MagicMock

import pytest

INTERNAL_LLM = "/internal/v1/llm"


@pytest.fixture(autouse=True)
def _ensure_openai_key_for_agent_tests():
    """call_llm_with_tools는 키가 없으면 OpenAI를 호출하지 않습니다."""
    from src.server.settings import settings

    prev = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = prev or "test-openai-key"
    yield
    settings.OPENAI_API_KEY = prev


@pytest.fixture
def capture_chat_kwargs(mock_openai_chat):
    """Record kwargs passed to OpenAI chat.completions.create."""
    calls = []

    async def chat_create(**kwargs):
        calls.append(kwargs)
        mock_message = MagicMock()
        mock_message.content = "모의 응답"
        mock_message.tool_calls = None
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.model = "gpt-4-turbo-preview"
        return mock_response

    mock_openai_chat.chat.completions.create = AsyncMock(side_effect=chat_create)
    return calls


def test_execute_includes_history_in_openai_messages(client, capture_chat_kwargs):
    """History from Java is forwarded in OpenAI messages (planning + final)."""
    response = client.post(
        f"{INTERNAL_LLM}/execute",
        json={
            "user_id": 1,
            "prompt": "마지막 질문",
            "history": [
                {"role": "user", "content": "첫 질문"},
                {"role": "assistant", "content": "첫 답변"},
            ],
            "context": {},
        },
    )
    assert response.status_code == 200
    assert len(capture_chat_kwargs) >= 2

    first_messages = capture_chat_kwargs[0]["messages"]
    assert first_messages[0]["role"] == "system"
    assert first_messages[1]["role"] == "user"
    assert first_messages[1]["content"] == "첫 질문"
    assert first_messages[2]["role"] == "assistant"
    assert first_messages[2]["content"] == "첫 답변"
    assert first_messages[-1]["role"] == "user"
    assert "마지막 질문" in first_messages[-1]["content"]

    second_messages = capture_chat_kwargs[1]["messages"]
    assert second_messages[0]["role"] == "system"
    assert second_messages[1]["role"] == "user"
    assert second_messages[2]["role"] == "assistant"
    assert second_messages[-1]["role"] == "user"
    assert "마지막 질문" in second_messages[-1]["content"]


def test_execute_stream_returns_sse_progress_and_complete(client, capture_chat_kwargs):
    """Stream endpoint emits progress and complete SSE events."""
    with client.stream(
        "POST",
        f"{INTERNAL_LLM}/execute/stream",
        json={
            "user_id": 1,
            "prompt": "스트림 테스트",
            "history": [],
            "context": {},
        },
    ) as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")

    assert "event: progress" in body
    assert "started" in body
    assert "event: complete" in body
    assert '"ok":' in body or '"ok": true' in body
