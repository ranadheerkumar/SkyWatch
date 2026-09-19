"""Unit tests for the Observability API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import Base, engine

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield


def _auth_headers() -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "demo@example.com", "password": "DemoPassword123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_deep_health_check_is_publicly_accessible():
    """Verify that /api/v1/observability/health does not require user authentication."""
    response = client.get("/api/v1/observability/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"healthy", "degraded"}
    assert "checks" in data
    assert "database" in data["checks"]
    assert "llm_providers" in data["checks"]
    assert "rate_limiter" in data["checks"]


def test_observability_metrics_requires_auth():
    """Verify that /api/v1/observability/metrics requires authorization."""
    unauth_response = client.get("/api/v1/observability/metrics")
    assert unauth_response.status_code == 401

    headers = _auth_headers()
    auth_response = client.get("/api/v1/observability/metrics", headers=headers)
    assert auth_response.status_code == 200
    data = auth_response.json()
    assert "rate_limiter_enabled" in data
