"""Tests for health check endpoints."""
import pytest


def test_health_check(client):
    """Test /healthz endpoint."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_readiness_check(client):
    """Test /readyz endpoint."""
    response = client.get("/readyz")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "checks" in data

