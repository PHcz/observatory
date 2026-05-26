"""BlitzortungClient tests against a localhost ``websockets.sync.server`` mock.

The mock accepts the ``{"a": 111}`` handshake and emits pre-captured real
Blitzortung frames (length-prefixed bin from ``tests/fixtures/blitzortung/sample_frames.bin``).
The client runs on a daemon thread so the test can drive shutdown via
``client.stopping = True``.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import observatory.pollers._write as _write_mod

websockets_sync_server = pytest.importorskip("websockets.sync.server")


# --- sd_notify mock ---------------------------------------------------------


class FakeNotifier:
    """Captures sd_notify .notify(msg) calls for assertion."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def notify(self, msg: str) -> None:
        self.calls.append(msg)


# --- DB rebind fixture ------------------------------------------------------


@pytest.fixture
def patched_db(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> Path:
    def _conn(_db_path: str | None = None) -> sqlite3.Connection:
        c = sqlite3.connect(str(tmp_db), isolation_level=None)
        c.execute("PRAGMA foreign_keys=ON")
        return c

    monkeypatch.setattr(_write_mod, "get_write_conn", _conn)
    return tmp_db


# --- Mock WS server ---------------------------------------------------------


@pytest.fixture
def mock_ws_server(load_frames: Callable[[], list[bytes]]):
    """Spawn a local websockets.sync.server on an ephemeral port.

    The server accepts ANY message (subscribe handshake) and streams the
    captured fixture frames once. Stays open until the test tears it down.
    """
    frames = load_frames()
    if not frames:
        pytest.skip("sample_frames.bin is the placeholder; run the network probe.")

    server_holder: dict[str, Any] = {}
    ready = threading.Event()

    def handler(ws: Any) -> None:
        try:
            _sub = ws.recv(timeout=5.0)  # consume subscribe
        except Exception:
            return
        for f in frames:
            try:
                ws.send(f)
            except Exception:
                return
        # Keep connection open until client closes.
        try:
            while True:
                try:
                    ws.recv(timeout=1.0)
                except Exception:
                    break
        except Exception:
            return

    def run() -> None:
        server = websockets_sync_server.serve(handler, "127.0.0.1", 0)
        server_holder["server"] = server
        server_holder["port"] = server.socket.getsockname()[1]
        ready.set()
        server.serve_forever()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    assert ready.wait(timeout=5.0), "mock WS server did not start in time"

    yield server_holder

    try:
        server_holder["server"].shutdown()
    except Exception:
        pass


# --- Helpers ----------------------------------------------------------------


def _make_client(
    url: str,
    *,
    radius_km: float = 1e7,
    flush_interval_sec: float = 0.2,
    degraded_after_sec: float = 60.0,
    notifier: FakeNotifier | None = None,
    backoff_override: tuple[float, ...] | None = None,
) -> Any:
    from observatory.pollers.blitzortung.client import BlitzortungClient

    n = notifier or FakeNotifier()
    client = BlitzortungClient(
        urls=[url],
        radius_km=radius_km,
        flush_interval_sec=flush_interval_sec,
        degraded_after_sec=degraded_after_sec,
        notifier=n,
        ssl_verify=False,  # mock uses plain ws://
    )
    if backoff_override is not None:
        from observatory.pollers.blitzortung import client as client_mod

        client._backoff_sequence_sec = backoff_override  # type: ignore[attr-defined]
        # Also patch module constant in case run path reads it.
        client_mod.BACKOFF_SEQUENCE_SEC = backoff_override  # type: ignore[attr-defined]
    return client, n


def _run_in_thread(client: Any) -> threading.Thread:
    t = threading.Thread(target=client.run, daemon=True)
    t.start()
    return t


def _wait_for(predicate: Callable[[], bool], timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


# --- Tests ------------------------------------------------------------------


def test_client_connects_decodes_and_flushes(patched_db: Path, mock_ws_server: dict) -> None:
    url = f"ws://127.0.0.1:{mock_ws_server['port']}"
    client, notifier = _make_client(url, radius_km=1e7, flush_interval_sec=0.2)
    t = _run_in_thread(client)
    try:
        assert _wait_for(lambda: _count_lightning_rows(patched_db) >= 5, timeout=5.0), (
            f"expected ≥5 rows, got {_count_lightning_rows(patched_db)}"
        )
    finally:
        client.stopping = True
        t.join(timeout=3.0)
    assert "READY=1" in notifier.calls


def test_client_filters_strikes_outside_radius(patched_db: Path, mock_ws_server: dict) -> None:
    url = f"ws://127.0.0.1:{mock_ws_server['port']}"
    # The pinned frames are from Mexico/USA (~-100 lon); London home with
    # 100km radius filters all of them out.
    client, _ = _make_client(url, radius_km=100.0, flush_interval_sec=0.2)
    t = _run_in_thread(client)
    try:
        # Wait long enough for frames to arrive + 1 flush
        time.sleep(1.0)
    finally:
        client.stopping = True
        t.join(timeout=3.0)
    assert _count_lightning_rows(patched_db) == 0


def test_client_emits_stopping_on_shutdown(patched_db: Path, mock_ws_server: dict) -> None:
    url = f"ws://127.0.0.1:{mock_ws_server['port']}"
    client, notifier = _make_client(url, radius_km=1e7, flush_interval_sec=0.2)
    t = _run_in_thread(client)
    try:
        _wait_for(lambda: "READY=1" in notifier.calls, timeout=3.0)
    finally:
        client.stopping = True
        t.join(timeout=3.0)
    assert "STOPPING=1" in notifier.calls


def test_client_reconnect_backoff_on_unreachable_url(patched_db: Path) -> None:
    """No server present at port 1 — client should attempt and back off, not crash."""
    from observatory.pollers.blitzortung.client import BlitzortungClient

    notifier = FakeNotifier()
    client = BlitzortungClient(
        urls=["ws://127.0.0.1:1"],  # ConnectionRefused
        radius_km=1e7,
        flush_interval_sec=0.1,
        degraded_after_sec=0.3,
        notifier=notifier,
        ssl_verify=False,
    )
    from observatory.pollers.blitzortung import client as client_mod

    client_mod.BACKOFF_SEQUENCE_SEC = (0.05, 0.05, 0.05, 0.05, 0.05)
    t = _run_in_thread(client)
    try:
        time.sleep(0.6)
        # Multiple attempts should have been made
        assert client._attempt >= 2  # type: ignore[attr-defined]
    finally:
        client.stopping = True
        t.join(timeout=2.0)
    # Restore
    client_mod.BACKOFF_SEQUENCE_SEC = (1, 2, 5, 10, 30)


def test_client_logs_degraded_when_no_data_arrives(patched_db: Path) -> None:
    """Connect never succeeds → after degraded_after_sec, INFO log fires once."""
    import structlog

    notifier = FakeNotifier()
    from observatory.pollers.blitzortung.client import BlitzortungClient

    client = BlitzortungClient(
        urls=["ws://127.0.0.1:1"],
        radius_km=1e7,
        flush_interval_sec=0.1,
        degraded_after_sec=0.2,
        notifier=notifier,
        ssl_verify=False,
    )
    from observatory.pollers.blitzortung import client as client_mod

    client_mod.BACKOFF_SEQUENCE_SEC = (0.05, 0.05, 0.05, 0.05, 0.05)

    with structlog.testing.capture_logs() as cap:
        t = _run_in_thread(client)
        try:
            time.sleep(0.8)
        finally:
            client.stopping = True
            t.join(timeout=2.0)

    degraded = [e for e in cap if e.get("event") == "lightning_poller_degraded"]
    assert len(degraded) >= 1, f"expected degraded log, got: {[e.get('event') for e in cap]}"
    client_mod.BACKOFF_SEQUENCE_SEC = (1, 2, 5, 10, 30)


# --- Module structure tests (no client construction) ------------------------


def test_no_lightningmaps_imports() -> None:
    """Open Q 2 — CONTEXT amended 2026-05-26 to drop LightningMaps."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    for sub in ("observatory", "tests", "deploy", "scripts"):
        for p in (root / sub).rglob("*.py"):
            text = p.read_text(errors="ignore")
            assert "lightningmaps" not in text.lower(), f"{p}: contains lightningmaps"
            assert "LIGHTNINGMAPS" not in text, f"{p}: contains LIGHTNINGMAPS"


def test_subscribe_message_in_client() -> None:
    """Client must send the literal {"a": 111} handshake (RESEARCH-locked)."""
    import inspect

    from observatory.pollers.blitzortung import client as client_mod

    src = inspect.getsource(client_mod)
    assert '"a": 111' in src


# --- Helpers ----------------------------------------------------------------


def _count_lightning_rows(db_path: Path) -> int:
    with sqlite3.connect(str(db_path)) as c:
        return c.execute("SELECT COUNT(*) FROM lightning_strikes").fetchone()[0]
