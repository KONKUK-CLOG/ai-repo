"""Tests for health check endpoints."""
import pytest


def test_health_check(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_check(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert set(data["checks"].keys()) == {
        "openai_api_key",
        "codebase_mongo_uri",
        "java_backend_base_url",
    }
    assert all(data["checks"].values())


@pytest.mark.parametrize(
    "field",
    ["OPENAI_API_KEY", "CODEBASE_MONGO_URI", "JAVA_BACKEND_BASE_URL"],
)
def test_readiness_not_ready_without_dependency(client, field):
    from src.server.settings import settings

    stash = getattr(settings, field)
    try:
        setattr(settings, field, None if field != "JAVA_BACKEND_BASE_URL" else "")
        response = client.get("/readyz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_ready"
        assert not all(data["checks"].values())
    finally:
        setattr(settings, field, stash)
