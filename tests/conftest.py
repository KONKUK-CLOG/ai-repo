"""Pytest configuration and shared fixtures."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.server.main import app
from src.server.settings import settings


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _test_env_settings():
    """Ensure /readyz checks pass unless a test overrides these."""
    prev_key = settings.OPENAI_API_KEY
    prev_mongo = settings.CODEBASE_MONGO_URI
    prev_java = settings.JAVA_BACKEND_BASE_URL
    settings.OPENAI_API_KEY = settings.OPENAI_API_KEY or "test-openai-key"
    settings.CODEBASE_MONGO_URI = settings.CODEBASE_MONGO_URI or "mongodb://127.0.0.1:27017"
    settings.JAVA_BACKEND_BASE_URL = settings.JAVA_BACKEND_BASE_URL or "http://127.0.0.1:9001"
    yield
    settings.OPENAI_API_KEY = prev_key
    settings.CODEBASE_MONGO_URI = prev_mongo
    settings.JAVA_BACKEND_BASE_URL = prev_java


@pytest.fixture
def mock_openai_chat():
    """Patch AsyncOpenAI in the agent module for non-streaming chat calls."""
    from types import SimpleNamespace

    with patch("src.server.routers.agent.AsyncOpenAI") as mock_client:
        mock_message = MagicMock()
        mock_message.content = '{"answer": "Test", "blog_markdown": "# Test\\n\\nBody"}'
        mock_message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.model = "gpt-4-turbo-preview"

        async def chat_create(**kwargs):
            return mock_response

        async def embed_create(**kwargs):
            mock_embedding_data = MagicMock()
            mock_embedding_data.embedding = [0.1] * 1536
            mock_embedding_response = MagicMock()
            mock_embedding_response.data = [mock_embedding_data]
            return mock_embedding_response

        chat_ns = SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=chat_create)))
        embeddings_ns = SimpleNamespace(create=AsyncMock(side_effect=embed_create))
        mock_instance = SimpleNamespace(chat=chat_ns, embeddings=embeddings_ns)

        mock_client.return_value = mock_instance
        yield mock_instance
