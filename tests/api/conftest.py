"""Shared FastAPI test fixtures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from observatory.api.main import app


@pytest.fixture
def api_client() -> TestClient:
    return TestClient(app)
