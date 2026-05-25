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


VALID_LINE_C = b"C,1,512,5000,3,21.3,1013.25,56-597-118\n"
VALID_LINE_T = b"T,2,256,5001,4,21.4,1013.30,56-597-118\n"
VALID_LINE_B = b"B,3,128,5002,5,21.5,1013.35,56-597-118\n"


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
    os.write(master_fd, b"C,1,512,3,4,21.3,1013.25,56-597-118\n")
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
    os.write(master_fd, b"C,1,100,3,4,21.0,1010.0,56-597-118\n")
    # Hand-crafted malformed line (wrong field count). Cache must NOT be cleared.
    os.write(master_fd, b"BROKEN,LINE\n")
    os.write(master_fd, b"T,2,200,3,4,22.5,1015.5,56-597-118\n")
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
    assert parsed["device_id"] == "56-597-118"


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
        line = f"T,{i},{i},5000,3,21.0,1013.0,56-597-118\n".encode()
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
