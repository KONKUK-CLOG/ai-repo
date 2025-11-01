"""Pytest configuration and fixtures."""
import pytest
from fastapi.testclient import TestClient
from src.server.main import app
from src.server.settings import settings


@pytest.fixture
def client():
    """Create test client.
    
    Returns:
        FastAPI test client
    """
    return TestClient(app)


@pytest.fixture
def api_headers():
    """Get API authentication headers.
    
    Returns:
        Headers dict with API key
    """
    return {"x-api-key": settings.SERVER_API_KEY}

