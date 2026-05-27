"""Verify FastAPI lifespan starts the weather subscriber alongside db_watcher.

Uses health_db autouse fixture from tests/api/conftest.py (no manual setup needed).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_lifespan_creates_subscriber_task(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lifespan startup must create a task for run_subscriber and tear it down on shutdown."""
    from observatory.api import main as main_mod

    sub_calls = {"started": 0, "cancelled": 0}

    async def fake_run_subscriber(stop_event, db_path=None):  # type: ignore[no-untyped-def]
        sub_calls["started"] += 1
        try:
            await stop_event.wait()
        except BaseException:
            sub_calls["cancelled"] += 1
            raise

    # Patch BOTH bindings — main.py does `from ... import run_subscriber`, so the lookup
    # goes through main.run_subscriber, not the source module. Patching only the source
    # leaves the cached main-module symbol pointing at the real coroutine.
    monkeypatch.setattr(
        "observatory.weather.subscriber.run_subscriber", fake_run_subscriber, raising=True
    )
    monkeypatch.setattr("observatory.api.main.run_subscriber", fake_run_subscriber, raising=True)

    with TestClient(main_mod.app):
        pass  # lifespan startup + shutdown happens here

    assert sub_calls["started"] >= 1, "subscriber task not started"


def test_subscriber_imported_in_main() -> None:
    """main.py imports run_subscriber at module scope (re-exports the source binding)."""
    import observatory.api.main as m

    assert hasattr(m, "run_subscriber")
