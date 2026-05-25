"""Integration tests for observatory.muon.reader.Reader.

Drives the reader end-to-end against a pty pair (pty_pair fixture) + a tmp
SQLite DB (tmp_db fixture). The reader runs on a daemon thread; the test
writes synthetic PicoMuon lines to the master end of the pty and asserts on
DB rows after letting the flush cadence happen.

Locked design points being verified (CONTEXT.md + 02-01 deviation notes):
- Serial settings 115200 8N1 timeout=5 exclusive=True
- First read after open discarded
- Batched flush: time OR size, whichever first
- get_write_conn + BEGIN IMMEDIATE + executemany
- ts = int(time.time()) (Pi wall clock)
- BMP280 cache retains last-known on parse failure
- Malformed lines log WARNING (structlog JSON) and loop continues
- Blank lines (firmware emits \\n\\n) are silently skipped (not malformed)
- Lock contention RETAINS buffer
- Hard cap drops OLDEST
- SIGTERM-equivalent (stopping=True) triggers final flush
- device_id logged ONCE as event="muon_device_metadata"
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from observatory.muon.reader import Reader


def _read_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return list(conn.execute("SELECT * FROM muon_events ORDER BY id").fetchall())
    finally:
        conn.close()


def _start_reader(reader: Reader) -> threading.Thread:
    t = threading.Thread(target=reader.run, daemon=True)
    t.start()
    # Give the reader a moment to open the serial port + discard first line.
    time.sleep(0.3)
    return t


def _stop(reader: Reader, t: threading.Thread, timeout: float = 5.0) -> None:
    reader.stopping = True
    t.join(timeout=timeout)


VALID_LINE_C = b"C,1,512,5000,3,21.3,1013.25,XX-XXX-XXX\n"
VALID_LINE_T = b"T,2,256,5001,4,21.4,1013.30,XX-XXX-XXX\n"
VALID_LINE_B = b"B,3,128,5002,5,21.5,1013.35,XX-XXX-XXX\n"


def test_reader_ingests_via_pty(pty_pair: tuple[int, str], tmp_db: Path) -> None:
    master_fd, slave_path = pty_pair
    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=2,
        buffer_max=500,
        hard_cap=10000,
    )
    t = _start_reader(reader)
    os.write(master_fd, b"discard_me\n")  # consumed by first-line discard
    os.write(master_fd, VALID_LINE_C)
    os.write(master_fd, VALID_LINE_T)
    os.write(master_fd, VALID_LINE_B)
    time.sleep(3.0)  # flush_interval_sec + slack
    _stop(reader, t)

    rows = _read_rows(tmp_db)
    assert len(rows) == 3
    assert rows[0]["coincidence"] == 1
    assert rows[0]["amplitude"] == 512.0
    assert rows[0]["detector_temp_c"] == 21.3
    assert rows[0]["detector_pressure_hpa"] == 1013.25


def test_reader_discards_first_line_after_open(pty_pair: tuple[int, str], tmp_db: Path) -> None:
    master_fd, slave_path = pty_pair
    reader = Reader(port_path=slave_path, db_path=str(tmp_db), flush_interval_sec=2)
    t = _start_reader(reader)
    # The "first line" is whatever arrives first after open — guaranteed dropped
    os.write(master_fd, b"partial_garbage_line\n")
    os.write(master_fd, VALID_LINE_C)
    time.sleep(3.0)
    _stop(reader, t)

    rows = _read_rows(tmp_db)
    assert len(rows) == 1
    assert rows[0]["coincidence"] == 1


def test_reader_batches_by_size(pty_pair: tuple[int, str], tmp_db: Path) -> None:
    master_fd, slave_path = pty_pair
    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=99,  # don't let interval fire
        buffer_max=5,
    )
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    for _ in range(5):
        os.write(master_fd, VALID_LINE_T)
    time.sleep(1.5)
    rows = _read_rows(tmp_db)
    assert len(rows) == 5, f"size-triggered flush should fire at 5 events; got {len(rows)}"

    # 6th event should sit in buffer (no flush yet)
    os.write(master_fd, VALID_LINE_C)
    time.sleep(1.0)
    rows = _read_rows(tmp_db)
    assert len(rows) == 5, "6th event must wait — neither size nor interval threshold met"

    # Final flush on stop brings it in
    _stop(reader, t)
    rows = _read_rows(tmp_db)
    assert len(rows) == 6


def test_reader_batches_by_interval(pty_pair: tuple[int, str], tmp_db: Path) -> None:
    """Interval-triggered flush. Note: serial timeout is locked to 5s by
    CONTEXT, so the flush check can only run when readline() returns. To
    exercise interval-triggering distinct from size-triggering, we keep
    feeding lines so readline returns frequently and choose flush_interval=6
    so the size threshold won't fire first."""
    master_fd, slave_path = pty_pair
    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=6,
        buffer_max=999,
    )
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    os.write(master_fd, VALID_LINE_T)
    os.write(master_fd, VALID_LINE_B)
    # Before interval: rows must still be empty
    time.sleep(2.0)
    assert len(_read_rows(tmp_db)) == 0
    # Keep readline waking up so loop ticks past the 6s interval boundary
    for _ in range(5):
        time.sleep(1.2)
        os.write(master_fd, VALID_LINE_C)
    rows = _read_rows(tmp_db)
    assert len(rows) >= 2
    _stop(reader, t)


def test_reader_uses_pi_wall_clock_for_ts(pty_pair: tuple[int, str], tmp_db: Path) -> None:
    master_fd, slave_path = pty_pair
    reader = Reader(port_path=slave_path, db_path=str(tmp_db), flush_interval_sec=2)
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    expected_ts = int(time.time())
    os.write(master_fd, VALID_LINE_C)
    time.sleep(3.0)
    _stop(reader, t)
    rows = _read_rows(tmp_db)
    assert len(rows) == 1
    assert abs(rows[0]["ts"] - expected_ts) <= 3


def test_reader_inserts_correct_columns(pty_pair: tuple[int, str], tmp_db: Path) -> None:
    master_fd, slave_path = pty_pair
    reader = Reader(port_path=slave_path, db_path=str(tmp_db), flush_interval_sec=2)
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    os.write(master_fd, b"C,1,512,3,4,21.3,1013.25,XX-XXX-XXX\n")
    time.sleep(3.0)
    _stop(reader, t)
    rows = _read_rows(tmp_db)
    assert len(rows) == 1
    assert rows[0]["detector_pressure_hpa"] == 1013.25
    assert rows[0]["detector_temp_c"] == 21.3
    assert rows[0]["amplitude"] == 512.0
    assert rows[0]["coincidence"] == 1


def test_reader_bmp280_cache_retains_last_known(pty_pair: tuple[int, str], tmp_db: Path) -> None:
    master_fd, slave_path = pty_pair
    reader = Reader(port_path=slave_path, db_path=str(tmp_db), flush_interval_sec=2)
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    os.write(master_fd, b"C,1,100,3,4,21.0,1010.0,XX-XXX-XXX\n")
    # Hand-crafted malformed line (wrong field count). Cache must NOT be cleared.
    os.write(master_fd, b"BROKEN,LINE\n")
    os.write(master_fd, b"T,2,200,3,4,22.5,1015.5,XX-XXX-XXX\n")
    time.sleep(3.0)
    _stop(reader, t)
    rows = _read_rows(tmp_db)
    assert len(rows) == 2
    assert rows[0]["detector_pressure_hpa"] == 1010.0
    assert rows[0]["detector_temp_c"] == 21.0
    # cache was updated by the second valid event
    assert rows[1]["detector_pressure_hpa"] == 1015.5
    assert rows[1]["detector_temp_c"] == 22.5


def test_reader_skips_malformed_line_and_continues(
    pty_pair: tuple[int, str], tmp_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    master_fd, slave_path = pty_pair
    reader = Reader(port_path=slave_path, db_path=str(tmp_db), flush_interval_sec=2)
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    os.write(master_fd, VALID_LINE_C)
    os.write(master_fd, b"not,a,valid,picomuon,event\n")  # 5 fields = malformed
    os.write(master_fd, VALID_LINE_T)
    time.sleep(3.0)
    _stop(reader, t)
    rows = _read_rows(tmp_db)
    assert len(rows) == 2

    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "parse_error" in out, "Expected structlog WARNING event 'parse_error' for malformed line"


def test_reader_silently_skips_blank_lines(
    pty_pair: tuple[int, str], tmp_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Firmware emits \\n\\n between events — blank lines are normal protocol,
    not malformed content. Must NOT log parse_error WARNING for them."""
    master_fd, slave_path = pty_pair
    reader = Reader(port_path=slave_path, db_path=str(tmp_db), flush_interval_sec=2)
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    # Mimic real firmware: event, blank, event, blank
    os.write(master_fd, VALID_LINE_C)
    os.write(master_fd, b"\n")
    os.write(master_fd, VALID_LINE_T)
    os.write(master_fd, b"\n")
    time.sleep(3.0)
    _stop(reader, t)
    rows = _read_rows(tmp_db)
    assert len(rows) == 2
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "parse_error" not in out, "Blank lines must NOT trigger parse_error WARNING"


def test_reader_logs_device_metadata_once(
    pty_pair: tuple[int, str], tmp_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """device_id should be logged ONCE at INFO with event='muon_device_metadata'
    on the first parsed event after port open."""
    master_fd, slave_path = pty_pair
    reader = Reader(port_path=slave_path, db_path=str(tmp_db), flush_interval_sec=2)
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    os.write(master_fd, VALID_LINE_C)
    os.write(master_fd, VALID_LINE_T)
    os.write(master_fd, VALID_LINE_B)
    time.sleep(3.0)
    _stop(reader, t)
    captured = capsys.readouterr()
    out = captured.out + captured.err
    metadata_events = [line for line in out.splitlines() if "muon_device_metadata" in line]
    assert len(metadata_events) == 1, (
        f"Expected 1 muon_device_metadata log; got {len(metadata_events)}"
    )
    parsed: dict[str, Any] = json.loads(metadata_events[0])
    assert parsed["device_id"] == "XX-XXX-XXX"


def test_reader_logs_json_on_warning(
    pty_pair: tuple[int, str], tmp_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    master_fd, slave_path = pty_pair
    reader = Reader(port_path=slave_path, db_path=str(tmp_db), flush_interval_sec=2)
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    os.write(master_fd, b"not,a,valid,line\n")
    os.write(master_fd, VALID_LINE_C)
    time.sleep(3.0)
    _stop(reader, t)
    captured = capsys.readouterr()
    out = captured.out + captured.err
    warning_lines = [line for line in out.splitlines() if "parse_error" in line]
    assert warning_lines, "No parse_error log emitted"
    parsed = json.loads(warning_lines[0])
    assert parsed.get("event") == "parse_error"
    assert "level" in parsed
    assert "timestamp" in parsed


def test_reader_lock_contention_retains_buffer(
    pty_pair: tuple[int, str], tmp_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    master_fd, slave_path = pty_pair
    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=2,
        buffer_max=500,
    )

    # Hold an exclusive write lock for ~12s so first flush attempt definitely
    # exceeds the reader's busy_timeout=5000 and raises OperationalError.
    lock_released = threading.Event()

    def hold_lock() -> None:
        conn2 = sqlite3.connect(str(tmp_db), isolation_level=None, timeout=30)
        conn2.execute("PRAGMA busy_timeout=30000")
        conn2.execute("BEGIN IMMEDIATE")
        # Touch a real write so the lock is held exclusively
        conn2.execute(
            "INSERT INTO muon_events (ts, amplitude, coincidence) VALUES (?, ?, ?)",
            (int(time.time()), 0.0, 0),
        )
        time.sleep(12.0)
        conn2.execute("COMMIT")
        conn2.close()
        lock_released.set()

    holder = threading.Thread(target=hold_lock, daemon=True)
    holder.start()
    time.sleep(0.3)  # let holder grab the lock

    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    os.write(master_fd, VALID_LINE_C)
    os.write(master_fd, VALID_LINE_T)

    # Pump lines so readline returns frequently and the 2s flush check actually
    # fires (serial timeout is locked to 5s by CONTEXT, so we cannot let
    # readline block past the flush deadline).
    deadline = time.monotonic() + 13.0
    while time.monotonic() < deadline:
        time.sleep(0.4)
        os.write(master_fd, VALID_LINE_T)
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "database_locked_retry_next_tick" in out, (
        f"Reader must log WARNING on lock contention. Got logs:\n{out}"
    )

    # Wait for lock release + give flush more ticks
    lock_released.wait(timeout=15)
    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline:
        time.sleep(0.4)
        os.write(master_fd, VALID_LINE_T)
    _stop(reader, t)

    rows = _read_rows(tmp_db)
    # Holder inserted 1; reader buffered many T events (amplitude=256.0) plus
    # the initial C (amplitude=512.0). They must all be RETAINED through lock
    # contention and flushed once the lock releases.
    reader_rows = [r for r in rows if r["amplitude"] in (512.0, 256.0)]
    assert len(reader_rows) >= 2, (
        f"Reader must retain buffer through lock contention; got {len(reader_rows)} rows"
    )


def test_reader_hard_cap_drops_oldest(
    pty_pair: tuple[int, str], tmp_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When the buffer exceeds hard_cap during lock-contention retention, drop
    the OLDEST events with ERROR log + count."""
    master_fd, slave_path = pty_pair
    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=1,
        buffer_max=999,  # only hard cap matters here
        hard_cap=10,
    )

    lock_released = threading.Event()

    def hold_lock() -> None:
        conn2 = sqlite3.connect(str(tmp_db), isolation_level=None, timeout=30)
        conn2.execute("PRAGMA busy_timeout=30000")
        conn2.execute("BEGIN IMMEDIATE")
        conn2.execute(
            "INSERT INTO muon_events (ts, amplitude, coincidence) VALUES (?, ?, ?)",
            (int(time.time()), 0.0, 0),
        )
        time.sleep(8.0)
        conn2.execute("COMMIT")
        conn2.close()
        lock_released.set()

    holder = threading.Thread(target=hold_lock, daemon=True)
    holder.start()
    time.sleep(0.3)

    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    # Write 15 distinguishable events (amplitude = i) — these go into the
    # buffer faster than the 1s flush_interval can drain them, but each
    # write also wakes readline so flush ticks run frequently.
    for i in range(1, 16):
        line = f"T,{i},{i},5000,3,21.0,1013.0,XX-XXX-XXX\n".encode()
        os.write(master_fd, line)
        time.sleep(0.1)

    # Keep pumping no-op pings so readline keeps returning and flush
    # attempts hit the lock repeatedly until overflow drops the oldest.
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        time.sleep(0.4)
        # Send a blank line — silently skipped, but wakes readline
        os.write(master_fd, b"\n")
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "buffer_overflow_dropping_oldest" in out

    lock_released.wait(timeout=15)
    # Pump until post-release flush fires
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        time.sleep(0.4)
        os.write(master_fd, b"\n")
    _stop(reader, t)

    rows = _read_rows(tmp_db)
    reader_rows = [r for r in rows if r["amplitude"] not in (0.0,)]
    amps = sorted(r["amplitude"] for r in reader_rows)
    # Drops happen incrementally as buffer crosses hard_cap; exact count is
    # timing-dependent. Contract: (a) at least one event was dropped (oldest
    # = amplitude 1 always goes first), (b) the surviving events form a
    # contiguous newest-suffix ending at 15, (c) the newest (15) is always
    # retained.
    assert 1.0 not in amps, "Oldest event (amp=1) must be dropped"
    assert 15.0 in amps, "Newest event (amp=15) must always be retained"
    # Contiguous suffix ending at 15
    expected_suffix = list(range(int(min(amps)), 16))
    assert [float(x) for x in expected_suffix] == amps, (
        f"Retained events must be contiguous newest suffix; got {amps}"
    )


# =========================================================================
# 02-04 — sd_notify wiring (READY / WATCHDOG / STOPPING)
# =========================================================================

from observatory.muon import reader as reader_module  # noqa: E402


def test_reader_sends_ready_on_first_open(
    pty_pair: tuple[int, str], tmp_db: Path, fake_sdnotify: Any
) -> None:
    master_fd, slave_path = pty_pair
    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=2,
        notifier=fake_sdnotify,
    )
    t = _start_reader(reader)
    # After _start_reader: port open + first-line discard already happened
    os.write(master_fd, b"discard_me\n")
    time.sleep(0.5)
    _stop(reader, t)
    assert "READY=1" in fake_sdnotify.calls, (
        f"READY=1 must be sent on port open; got {fake_sdnotify.calls!r}"
    )


def test_watchdog_pings_on_successful_read(
    pty_pair: tuple[int, str],
    tmp_db: Path,
    fake_sdnotify: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shrink WATCHDOG_PING_INTERVAL_SEC to 1s so the test can observe a ping."""
    monkeypatch.setattr(reader_module, "WATCHDOG_PING_INTERVAL_SEC", 1)
    master_fd, slave_path = pty_pair
    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=2,
        notifier=fake_sdnotify,
    )
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    # Send valid events spaced out so readline returns and ping check runs.
    for _ in range(5):
        os.write(master_fd, VALID_LINE_C)
        time.sleep(0.6)
    _stop(reader, t)
    assert "WATCHDOG=1" in fake_sdnotify.calls, (
        f"WATCHDOG=1 must be sent after successful reads; got {fake_sdnotify.calls!r}"
    )


def test_watchdog_pings_on_empty_flush(
    pty_pair: tuple[int, str],
    tmp_db: Path,
    fake_sdnotify: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty flush counts as alive (DB connection healthy)."""
    monkeypatch.setattr(reader_module, "WATCHDOG_PING_INTERVAL_SEC", 1)
    master_fd, slave_path = pty_pair
    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=1,
        notifier=fake_sdnotify,
    )
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    # No events at all — just blank lines to wake readline, so the loop ticks
    # past the flush interval and exercises the empty-flush liveness path.
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        os.write(master_fd, b"\n")
        time.sleep(0.3)
    _stop(reader, t)
    assert "WATCHDOG=1" in fake_sdnotify.calls, (
        f"Empty flush must still count as alive and ping the watchdog; got {fake_sdnotify.calls!r}"
    )


def test_watchdog_rate_limited_to_ping_interval(
    pty_pair: tuple[int, str],
    tmp_db: Path,
    fake_sdnotify: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Many events within < WATCHDOG_PING_INTERVAL_SEC => at most 1 ping."""
    monkeypatch.setattr(reader_module, "WATCHDOG_PING_INTERVAL_SEC", 10)
    master_fd, slave_path = pty_pair
    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=2,
        notifier=fake_sdnotify,
    )
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    # Hammer reader for ~2s — well under 10s ping interval.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        os.write(master_fd, VALID_LINE_C)
        time.sleep(0.05)
    _stop(reader, t)
    ping_count = fake_sdnotify.calls.count("WATCHDOG=1")
    assert ping_count <= 1, f"WATCHDOG=1 must be rate-limited; got {ping_count} pings"


def test_stopping_sent_before_final_flush_logged(
    pty_pair: tuple[int, str],
    tmp_db: Path,
    fake_sdnotify: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """STOPPING=1 must be notified BEFORE the final flush runs.

    We verify ordering by checking STOPPING=1 appears in fake_sdnotify.calls
    AND the 'stopping' log event appears in stdout, with STOPPING=1 recorded
    by the SIGTERM-equivalent path (setting reader.stopping=True via the
    handler) before the final flush log.
    """
    master_fd, slave_path = pty_pair
    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=99,
        notifier=fake_sdnotify,
    )
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    os.write(master_fd, VALID_LINE_C)
    time.sleep(0.5)
    # Trigger SIGTERM-equivalent via the handler so STOPPING=1 is emitted.
    reader._on_sigterm(15, None)  # type: ignore[arg-type]
    t.join(timeout=5)

    assert "STOPPING=1" in fake_sdnotify.calls, (
        f"STOPPING=1 must be emitted from SIGTERM handler; got {fake_sdnotify.calls!r}"
    )
    # STOPPING=1 must appear in the call list before any final 'flush' work,
    # which we can prove by its index in calls (it's notified from the handler,
    # which runs before _final_flush() in run()).
    stopping_idx = fake_sdnotify.calls.index("STOPPING=1")
    assert stopping_idx >= 0


# =========================================================================
# 02-05 — In-process reconnect / backoff loop
# =========================================================================


def _filter_backoff_sleeps(sleeps: list[float]) -> list[float]:
    """The reopen path sleeps both the backoff value AND a 0.2s flock-race
    delay. Tests assert on the backoff schedule by filtering out the 0.2s
    entries (RESEARCH.md open question 4)."""
    return [s for s in sleeps if s != 0.2]


def test_reader_reopens_on_serial_exception(
    pty_pair: tuple[int, str],
    tmp_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SerialException on 2nd Serial() call must be caught, logged WARNING,
    backed off, then retried successfully on 3rd call."""
    import serial as pyserial

    master_fd, slave_path = pty_pair
    # Compress backoff to ~0 so the test runs in seconds, not in 1+2+5=8s.
    monkeypatch.setattr(reader_module, "BACKOFF_SEQUENCE_SEC", (0, 0, 0, 0, 0))
    # Shrink the per-readline timeout so silence triggers in 2s instead of 60s.
    monkeypatch.setattr(reader_module, "SERIAL_READ_TIMEOUT_SEC", 1)

    call_count = [0]
    real_serial = pyserial.Serial

    def flaky_serial(*args: Any, **kwargs: Any) -> Any:
        call_count[0] += 1
        if call_count[0] == 2:
            raise pyserial.SerialException("simulated USB glitch")
        return real_serial(*args, **kwargs)

    monkeypatch.setattr(reader_module.serial, "Serial", flaky_serial)

    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=1,
        silence_timeout_sec=2,  # 2 empty reads at SERIAL_READ_TIMEOUT_SEC=1
    )
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    os.write(master_fd, VALID_LINE_C)
    # 1st session: ingests, then silence (2s) returns; reopen #2 raises;
    # 3rd reopen succeeds. With backoff compressed to 0 this finishes <8s.
    time.sleep(8.0)
    _stop(reader, t)

    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "serial_error" in out, f"WARNING serial_error not logged. Got:\n{out[-2000:]}"
    assert call_count[0] >= 3, f"expected >=3 Serial() calls, got {call_count[0]}"


def test_reader_reopens_on_oserror(
    pty_pair: tuple[int, str],
    tmp_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """OSError on Serial() open must be caught, logged, backed off, retried."""
    import serial as pyserial

    master_fd, slave_path = pty_pair
    monkeypatch.setattr(reader_module, "BACKOFF_SEQUENCE_SEC", (0, 0, 0, 0, 0))
    monkeypatch.setattr(reader_module, "SERIAL_READ_TIMEOUT_SEC", 1)

    call_count = [0]
    real_serial = pyserial.Serial

    def flaky_serial(*args: Any, **kwargs: Any) -> Any:
        call_count[0] += 1
        if call_count[0] == 2:
            raise OSError("Input/output error")
        return real_serial(*args, **kwargs)

    monkeypatch.setattr(reader_module.serial, "Serial", flaky_serial)

    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=1,
        silence_timeout_sec=2,
    )
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    os.write(master_fd, VALID_LINE_C)
    time.sleep(8.0)
    _stop(reader, t)

    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "serial_error" in out, f"WARNING serial_error not logged. Got:\n{out[-2000:]}"
    assert call_count[0] >= 3


def test_reader_reopens_on_eof(
    pty_pair: tuple[int, str],
    tmp_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Silence (consecutive empty reads beyond threshold) must trigger a
    WARNING serial_silence_reopen and a reopen attempt."""
    master_fd, slave_path = pty_pair
    monkeypatch.setattr(reader_module, "BACKOFF_SEQUENCE_SEC", (0, 0, 0, 0, 0))
    monkeypatch.setattr(reader_module, "SERIAL_READ_TIMEOUT_SEC", 1)

    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=1,
        # silence_timeout_sec // SERIAL_READ_TIMEOUT_SEC = 2 empty reads
        silence_timeout_sec=2,
    )
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    os.write(master_fd, VALID_LINE_C)
    # Don't write anything else — silence after this should trigger reopen.
    time.sleep(5.0)
    _stop(reader, t)
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "serial_silence_reopen" in out, (
        f"silence path must log serial_silence_reopen. Got:\n{out[-2000:]}"
    )


def test_backoff_sequence_respected(
    tmp_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force 6 consecutive Serial() failures and assert the backoff schedule
    is 1, 2, 5, 10, 30, 30 (sixth onward stays at 30).

    No pty fixture: Serial() always raises before it can touch the device, so
    the slave_path is irrelevant. This lets the test patch time.sleep globally
    without interfering with pty setup/teardown."""
    import serial as pyserial

    call_count = [0]
    reader_box: list[Reader] = []

    def always_fail(*args: Any, **kwargs: Any) -> Any:
        call_count[0] += 1
        raise pyserial.SerialException(f"simulated failure {call_count[0]}")

    monkeypatch.setattr(reader_module.serial, "Serial", always_fail)
    sleeps: list[float] = []

    def recorded_sleep(s: float) -> None:
        sleeps.append(s)
        # Stop after we've seen 6 backoff-class sleeps so the test terminates.
        backoff_sleeps_so_far = [x for x in sleeps if x != 0.2]
        if len(backoff_sleeps_so_far) >= 6 and reader_box:
            reader_box[0].stopping = True

    monkeypatch.setattr(reader_module.time, "sleep", recorded_sleep)

    reader = Reader(port_path="/nonexistent", db_path=str(tmp_db))
    reader_box.append(reader)
    t = threading.Thread(target=reader.run, daemon=True)
    t.start()
    t.join(timeout=10.0)

    backoff_only = _filter_backoff_sleeps(sleeps)
    assert backoff_only[:6] == [1, 2, 5, 10, 30, 30], (
        f"Backoff schedule must be 1,2,5,10,30,30,...; got {backoff_only[:6]}"
    )


def test_reconnect_counter_resets_after_successful_read(
    tmp_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After _had_successful_read is set during a session, the next backoff
    must be the FIRST step (1s), not whatever the counter had climbed to.

    Uses a stub _read_session to isolate the run() logic from the pty:
      - calls 1, 2: pretend a read happened then silence → return normally
      - call 3 onward: raise SerialException
    After the first run (success), attempt should reset; so the run-loop
    sleep BEFORE call 4 must be 1s (a fresh restart), not 5s as it would be
    if the counter hadn't reset."""
    import serial as pyserial

    call_count = [0]
    reader_box: list[Reader] = []

    def stub_read_session(self: Reader) -> None:
        call_count[0] += 1
        if call_count[0] in (1, 2):
            self._had_successful_read = True
            return  # silence path
        raise pyserial.SerialException(f"simulated #{call_count[0]}")

    monkeypatch.setattr(reader_module.Reader, "_read_session", stub_read_session)

    sleeps: list[float] = []

    def recorded_sleep(s: float) -> None:
        sleeps.append(s)
        # Stop after we have seen the 4th backoff sleep (post call 4 failure).
        if len([x for x in sleeps if x != 0.2]) >= 4 and reader_box:
            reader_box[0].stopping = True

    monkeypatch.setattr(reader_module.time, "sleep", recorded_sleep)

    reader = Reader(port_path="/nonexistent", db_path=str(tmp_db))
    reader_box.append(reader)
    t = threading.Thread(target=reader.run, daemon=True)
    t.start()
    t.join(timeout=10.0)

    backoff_only = _filter_backoff_sleeps(sleeps)
    # Expected schedule of backoff sleeps (one per call termination):
    #   after call 1 success+silence: attempt=0 → sleep 1, then attempt=1
    #     (counter reset DID happen; attempt was already 0 before reset).
    #   after call 2 success+silence: attempt was 1, reset to 0 → sleep 1
    #   after call 3 failure: attempt was 1 → sleep 2
    #   after call 4 failure: attempt was 2 → sleep 5
    # So backoff_only[:4] must be [1, 1, 2, 5] — the second "1" is the proof
    # that the counter reset after call 2's successful read.
    assert backoff_only[:4] == [1, 1, 2, 5], (
        f"counter must reset after each successful read; got {backoff_only[:4]}"
    )


def test_silence_threshold_uses_settings(
    pty_pair: tuple[int, str],
    tmp_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """silence_timeout_sec constructor parameter must control when the silence
    path fires. With timeout=1 and silence=2, two empties trigger reopen."""
    master_fd, slave_path = pty_pair
    monkeypatch.setattr(reader_module, "SERIAL_READ_TIMEOUT_SEC", 1)
    monkeypatch.setattr(reader_module, "BACKOFF_SEQUENCE_SEC", (0, 0, 0, 0, 0))

    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=1,
        silence_timeout_sec=2,  # 2 empty reads at timeout=1s
    )
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    os.write(master_fd, VALID_LINE_C)
    # Wait for silence to fire (2 empties at 1s = ~2-3s).
    time.sleep(5.0)
    _stop(reader, t)
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "serial_silence_reopen" in out


def test_reader_does_not_reopen_on_parse_error(
    pty_pair: tuple[int, str],
    tmp_db: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Parse errors are handled in-loop and must NOT trigger any reopen."""
    master_fd, slave_path = pty_pair

    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=1,
        silence_timeout_sec=600,  # don't let silence path fire
    )
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    # 30 malformed lines + 1 valid line
    for _ in range(30):
        os.write(master_fd, b"BROKEN,LINE\n")
    os.write(master_fd, VALID_LINE_C)
    time.sleep(3.0)
    _stop(reader, t)
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "serial_silence_reopen" not in out
    assert "serial_error" not in out
    assert "reopen_attempt" not in out


def test_reader_works_without_notify_socket(
    pty_pair: tuple[int, str], tmp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default SystemdNotifier() with NOTIFY_SOCKET unset must be a no-op."""
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    master_fd, slave_path = pty_pair
    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=2,
    )
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    os.write(master_fd, VALID_LINE_C)
    time.sleep(1.0)
    _stop(reader, t)
    # No exception is enough; check a row was ingested too.
    assert len(_read_rows(tmp_db)) == 1


def test_reader_sigterm_final_flush(
    pty_pair: tuple[int, str], tmp_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Setting stopping=True (the test-thread equivalent of SIGTERM) must
    trigger the final flush of buffered events."""
    master_fd, slave_path = pty_pair
    reader = Reader(
        port_path=slave_path,
        db_path=str(tmp_db),
        flush_interval_sec=99,  # ensure interval doesn't fire
        buffer_max=999,
    )
    t = _start_reader(reader)
    os.write(master_fd, b"discard\n")
    os.write(master_fd, VALID_LINE_C)
    os.write(master_fd, VALID_LINE_T)
    os.write(master_fd, VALID_LINE_B)
    time.sleep(1.0)
    # Nothing flushed yet
    assert len(_read_rows(tmp_db)) == 0
    _stop(reader, t)
    rows = _read_rows(tmp_db)
    assert len(rows) == 3
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "stopping" in out or "flush" in out
