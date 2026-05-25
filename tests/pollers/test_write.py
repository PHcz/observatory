"""Writer + dedup + poller_runs (two-transaction) + compute_parse_outcome."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from observatory.pollers._types import EarthquakeEvent
from observatory.pollers._write import compute_parse_outcome, write_events


def _patch_get_write_conn(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    def _factory(_path: str | None = None) -> sqlite3.Connection:
        from observatory.db.connection import get_conn

        return get_conn(str(db_path))

    monkeypatch.setattr("observatory.pollers._write.get_write_conn", _factory)


def _ev(external_id: str, ts: int = 1779700000) -> EarthquakeEvent:
    return EarthquakeEvent(
        source="usgs",
        external_id=external_id,
        ts=ts,
        magnitude=5.0,
        depth_km=10.0,
        latitude=1.0,
        longitude=2.0,
        place="somewhere",
    )


# --- Writer / dedup / poller_runs ---


def test_write_inserts_events(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    _patch_get_write_conn(monkeypatch, tmp_db)
    events = [_ev("a"), _ev("b"), _ev("c")]
    fetched, written = write_events("usgs", events, started_at=1, status="success")
    assert (fetched, written) == (3, 3)
    rows = sqlite3.connect(str(tmp_db)).execute("SELECT COUNT(*) FROM earthquakes").fetchone()
    assert rows[0] == 3


def test_write_dedup(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    _patch_get_write_conn(monkeypatch, tmp_db)
    events = [_ev("a"), _ev("b"), _ev("c")]
    write_events("usgs", events, started_at=1, status="success")
    fetched, written = write_events("usgs", events, started_at=2, status="success")
    assert (fetched, written) == (3, 0)


def test_write_partial_dedup(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    _patch_get_write_conn(monkeypatch, tmp_db)
    write_events("usgs", [_ev("a"), _ev("b")], started_at=1, status="success")
    fetched, written = write_events("usgs", [_ev("b"), _ev("c")], started_at=2, status="success")
    assert (fetched, written) == (2, 1)


def test_write_emits_poller_runs_row_on_success(
    monkeypatch: pytest.MonkeyPatch, tmp_db: Path
) -> None:
    _patch_get_write_conn(monkeypatch, tmp_db)
    write_events("usgs", [_ev("a"), _ev("b")], started_at=100, status="success")
    rows = (
        sqlite3.connect(str(tmp_db))
        .execute(
            "SELECT source, started_at, status, events_fetched, events_written, error_summary "
            "FROM poller_runs"
        )
        .fetchall()
    )
    assert len(rows) == 1
    assert rows[0][0] == "usgs"
    assert rows[0][1] == 100
    assert rows[0][2] == "success"
    assert rows[0][3] == 2
    assert rows[0][4] == 2
    assert rows[0][5] is None


def test_write_empty_events_still_emits_poller_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_db: Path
) -> None:
    _patch_get_write_conn(monkeypatch, tmp_db)
    fetched, written = write_events("usgs", [], started_at=1, status="success")
    assert (fetched, written) == (0, 0)
    rows = (
        sqlite3.connect(str(tmp_db))
        .execute("SELECT events_fetched, events_written, status FROM poller_runs")
        .fetchall()
    )
    assert rows == [(0, 0, "success")]


def test_write_failure_status_with_error_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_db: Path
) -> None:
    _patch_get_write_conn(monkeypatch, tmp_db)
    long_err = "x" * 500
    write_events("usgs", [], started_at=1, status="network_unreachable", error_summary=long_err)
    rows = (
        sqlite3.connect(str(tmp_db))
        .execute("SELECT status, error_summary FROM poller_runs")
        .fetchall()
    )
    assert rows[0][0] == "network_unreachable"
    assert rows[0][1] is not None
    assert len(rows[0][1]) == 200  # truncated


def test_poller_runs_emitted_in_separate_transaction(
    monkeypatch: pytest.MonkeyPatch, tmp_db: Path
) -> None:
    """If the events INSERT throws, the poller_runs audit row STILL lands."""
    _patch_get_write_conn(monkeypatch, tmp_db)
    # Force an integrity error by passing an event with a non-encodable field type.
    bad_event = EarthquakeEvent(
        source="usgs",
        external_id="bad",
        ts=1,
        magnitude=float("nan"),  # acceptable; we sabotage differently below
        depth_km=None,
        latitude=1.0,
        longitude=2.0,
        place=object(),  # type: ignore[arg-type]  # sqlite3 will refuse this
    )
    write_events("usgs", [bad_event], started_at=42, status="success")
    rows = (
        sqlite3.connect(str(tmp_db))
        .execute("SELECT status, started_at FROM poller_runs")
        .fetchall()
    )
    assert len(rows) == 1
    assert rows[0][0] == "db_fail"
    assert rows[0][1] == 42


def test_rowcount_per_execute_not_executemany() -> None:
    import observatory.pollers._write as wm

    src = open(wm.__file__).read()
    assert "executemany" not in src


# --- compute_parse_outcome ---


def test_parse_outcome_all_good_returns_success() -> None:
    assert compute_parse_outcome(good=10, failures=0, threshold=0.5) == ("success", None)


def test_parse_outcome_under_threshold_returns_success() -> None:
    assert compute_parse_outcome(good=8, failures=2, threshold=0.5) == ("success", None)


def test_parse_outcome_at_threshold_returns_success() -> None:
    # Boundary: ratio == threshold is NOT a failure ("exceeds 50%")
    assert compute_parse_outcome(good=5, failures=5, threshold=0.5) == ("success", None)


def test_parse_outcome_over_threshold_returns_parse_fail() -> None:
    status, summary = compute_parse_outcome(good=2, failures=8, threshold=0.5)
    assert status == "parse_fail"
    assert summary is not None
    assert "0.80" in summary or "8/10" in summary


def test_parse_outcome_only_failures_returns_parse_fail() -> None:
    status, summary = compute_parse_outcome(good=0, failures=5, threshold=0.5)
    assert status == "parse_fail"
    assert summary is not None


def test_parse_outcome_zero_total_returns_success() -> None:
    assert compute_parse_outcome(good=0, failures=0, threshold=0.5) == ("success", None)


def test_parse_outcome_uses_settings_default_threshold() -> None:
    status, _ = compute_parse_outcome(good=2, failures=8)
    assert status == "parse_fail"
