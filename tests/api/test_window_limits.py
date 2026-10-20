"""Time-series window limits (security audit 2026-10-20, M3).

`from`/`to` were unbounded. The cost is rows SCANNED, not rows returned: the
muon table is dense (~150 events/min, 34.6 M rows), so even agg=day over 30 days
scanned ~6.5 M rows -- measured at 60 s of Pi CPU, with a few concurrent
requests enough to starve the WebSocket watcher. Weather is ~288 rows/day, so a
year of it is cheap. Limits are therefore per table, and sized so the dashboard's
own requests (24 h windows, agg=auto) are untouched.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.api.routers import muon as muon_router
from observatory.api.routers import space_weather as sw_router
from observatory.api.routers import weather as weather_router

HOUR, DAY = 3600, 86400


@pytest.fixture
def client(_ensure_settings_loaded: Path) -> TestClient:
    app = FastAPI()
    for r in (muon_router, weather_router, sw_router):
        app.include_router(r.router, prefix="/api")
    return TestClient(app)


def _get(client: TestClient, path: str, span: int, agg: str = "auto") -> int:
    to = int(time.time())
    code: int = client.get(f"/api/{path}?from={to - span}&to={to}&agg={agg}").status_code
    return code


@pytest.mark.parametrize("path", ["muon", "weather"])
def test_the_dashboards_own_requests_still_work(client: TestClient, path: str) -> None:
    """MuonChart / TemperatureChart / PressureChart all ask for 24 h, agg=auto."""
    assert _get(client, path, DAY) == 200


@pytest.mark.parametrize(
    ("span", "agg"),
    [(30 * DAY, "auto"), (30 * DAY, "day"), (7 * DAY, "hour"), (DAY, "raw")],
)
def test_muon_rejects_windows_that_scan_millions_of_rows(
    client: TestClient, span: int, agg: str
) -> None:
    assert _get(client, "muon", span, agg) == 422


def test_muon_allows_two_days_bucketed_and_two_hours_raw(client: TestClient) -> None:
    assert _get(client, "muon", 2 * DAY, "minute") == 200
    assert _get(client, "muon", 2 * HOUR, "raw") == 200


@pytest.mark.parametrize("path", ["weather", "space-weather"])
def test_sparse_tables_allow_a_year(client: TestClient, path: str) -> None:
    assert _get(client, path, 365 * DAY) == 200


@pytest.mark.parametrize(
    ("path", "span", "agg"),
    [
        ("weather", 2 * 365 * DAY, "auto"),
        ("weather", 60 * DAY, "raw"),
        ("space-weather", 2 * 365 * DAY, "auto"),
    ],
)
def test_sparse_tables_still_have_a_ceiling(
    client: TestClient, path: str, span: int, agg: str
) -> None:
    assert _get(client, path, span, agg) == 422


def test_rejection_says_what_the_limit_is(client: TestClient) -> None:
    to = int(time.time())
    body = client.get(f"/api/muon?from={to - 30 * DAY}&to={to}").json()
    assert "window" in str(body.get("detail", "")).lower()
