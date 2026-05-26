"""AuroraWatch UK e2e tests for `python -m observatory.pollers.aurorawatch`.

Mirrors the BGS e2e test shape: monkeypatches fetch + get_write_conn, runs
main(), asserts on aurora_status + poller_runs rows.

Required scenarios (POLL-06):
- Happy path: writes 1 aurora_status row, poller_runs status='success'
- Network failure: 0 rows, poller_runs status='transient_fail'
- Parse failure: 0 rows, poller_runs status='parse_fail'
- Subsequent good run after parse_fail still works (ROADMAP criterion 2)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import observatory.pollers._http as _http_mod
import observatory.pollers._write as _write_mod
from observatory.pollers._http import RetriesExhausted
from observatory.pollers.aurorawatch.__main__ import main as aurora_main


@pytest.fixture
def patched_db(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> Path:
    def _conn(_db_path: str | None = None) -> sqlite3.Connection:
        c = sqlite3.connect(str(tmp_db), isolation_level=None)
        c.execute("PRAGMA foreign_keys=ON")
        return c

    monkeypatch.setattr(_write_mod, "get_write_conn", _conn)
    return tmp_db


def _install_fetch(monkeypatch: pytest.MonkeyPatch, body_or_exc: bytes | Exception) -> None:
    def fake_fetch(url: str, *, source: str, **_kw: object) -> bytes:
        if isinstance(body_or_exc, Exception):
            raise body_or_exc
        if isinstance(body_or_exc, bytes):
            return body_or_exc
        raise AssertionError("unreachable")

    import observatory.pollers.aurorawatch.__main__ as _main_mod

    monkeypatch.setattr(_http_mod, "fetch", fake_fetch)
    monkeypatch.setattr(_main_mod, "fetch", fake_fetch)


# ---------- Tests ----------


def test_main_writes_aurora_row(
    monkeypatch: pytest.MonkeyPatch,
    patched_db: Path,
    fixtures_dir: Path,
) -> None:
    body = (fixtures_dir / "aurora" / "current_status_sample.xml").read_bytes()
    _install_fetch(monkeypatch, body)
    rc = aurora_main()
    assert rc == 0
    conn = sqlite3.connect(str(patched_db))
    rows = conn.execute("SELECT ts, status, detail FROM aurora_status").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "green"
    assert rows[0][2] == "project:SAMNET:site:SAMNET:CRK2"
    status = conn.execute(
        "SELECT status FROM poller_runs WHERE source='aurora' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    assert status == "success"
    conn.close()


def test_main_network_failure_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path
) -> None:
    _install_fetch(monkeypatch, RetriesExhausted("simulated"))
    rc = aurora_main()
    assert rc == 1
    conn = sqlite3.connect(str(patched_db))
    n = conn.execute("SELECT COUNT(*) FROM aurora_status").fetchone()[0]
    assert n == 0
    row = conn.execute(
        "SELECT status, error_summary FROM poller_runs WHERE source='aurora' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row[0] == "transient_fail"
    assert "simulated" in (row[1] or "")
    conn.close()


def test_main_parse_fail_writes_poller_runs_parse_fail_exit_nonzero(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path
) -> None:
    _install_fetch(monkeypatch, b"<not-xml")
    rc = aurora_main()
    assert rc == 1
    conn = sqlite3.connect(str(patched_db))
    n = conn.execute("SELECT COUNT(*) FROM aurora_status").fetchone()[0]
    assert n == 0
    row = conn.execute(
        "SELECT status, error_summary FROM poller_runs WHERE source='aurora' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row[0] == "parse_fail"
    assert row[1] is not None
    conn.close()


def test_main_recovers_after_parse_fail(
    monkeypatch: pytest.MonkeyPatch,
    patched_db: Path,
    fixtures_dir: Path,
) -> None:
    """ROADMAP criterion 2: XML parse failure causes a retry log, not a crash.

    First run with malformed XML -> exit 1, parse_fail.
    Second run with good XML -> exit 0, row written, success.
    """
    _install_fetch(monkeypatch, b"<not-xml")
    assert aurora_main() == 1

    body = (fixtures_dir / "aurora" / "current_status_sample.xml").read_bytes()
    _install_fetch(monkeypatch, body)
    assert aurora_main() == 0

    conn = sqlite3.connect(str(patched_db))
    n = conn.execute("SELECT COUNT(*) FROM aurora_status").fetchone()[0]
    assert n == 1
    runs = conn.execute(
        "SELECT status FROM poller_runs WHERE source='aurora' ORDER BY id ASC"
    ).fetchall()
    assert [r[0] for r in runs] == ["parse_fail", "success"]
    conn.close()


def test_main_unknown_status_id_is_parse_fail(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path
) -> None:
    """An unknown status_id (e.g. 'blue') must NOT crash — recorded as parse_fail."""
    body = (
        b'<?xml version="1.0"?>'
        b'<current_status api_version="0.2.5">'
        b"<updated><datetime>2026-05-25T22:48:32+0000</datetime></updated>"
        b'<site_status project_id="p" site_id="s" status_id="blue"/>'
        b"</current_status>"
    )
    _install_fetch(monkeypatch, body)
    rc = aurora_main()
    assert rc == 1
    conn = sqlite3.connect(str(patched_db))
    n = conn.execute("SELECT COUNT(*) FROM aurora_status").fetchone()[0]
    assert n == 0
    status = conn.execute(
        "SELECT status FROM poller_runs WHERE source='aurora' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    assert status == "parse_fail"
    conn.close()
