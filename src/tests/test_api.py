"""Smoke tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_config_endpoint(client):
    """Test config endpoint."""
    response = client.get("/config")
    assert response.status_code == 200
    data = response.json()
    assert "project_endpoint" in data
