"""Tests for health check endpoints."""

from fastapi.testclient import TestClient


def test_health_check_status_code(client: TestClient):
    """Test that GET /health returns HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_check_payload_structure(client: TestClient):
    """Test that GET /health returns expected schema fields."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "RecoverAI"
    assert "environment" in data
    assert "version" in data
    assert "components" in data

    components = data["components"]
    assert "database" in components
    assert "redis" in components


def test_api_v1_health_check(client: TestClient):
    """Test that GET /api/v1/health returns HTTP 200 with consistent payload."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_root_endpoint(client: TestClient):
    """Test that GET / returns root service metadata and discovery links."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "RecoverAI"
    assert data["status"] == "operational"
    assert data["health"] == "/health"
    assert data["docs"] == "/docs"
