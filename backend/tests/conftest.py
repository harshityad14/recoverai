"""Pytest test fixtures and configuration."""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Provides a TestClient instance for issuing requests against the FastAPI application.

    Yields:
        TestClient: Initialized client.
    """
    with TestClient(app) as test_client:
        yield test_client
