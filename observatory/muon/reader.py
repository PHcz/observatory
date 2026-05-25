"""PicoMuon serial reader — I/O spine of the muon service.

Owns: serial port, in-memory event buffer, BMP280 last-known cache, batched
SQLite flush, SIGTERM/SIGINT graceful shutdown, malformed-line tolerance with
rate-limited WARNING, in-process reopen-on-failure loop with backoff.

Locked design decisions (from 02-CONTEXT.md):
- Serial: 115200 8N1, timeout=5, exclusive=True (POSIX) — blocks screen/minicom races
- First read after open is discarded — avoids guaranteed mid-event partial
- BMP280 last-known cache; row uses cache values (defends against partial lines)
- Flush every flush_interval_sec OR when buffer reaches buffer_max
- One transaction: BEGIN IMMEDIATE + executemany + COMMIT via get_write_conn()
- Lock contention (OperationalError 'database is locked'): WARNING, RETAIN buffer,
  retry next tick. Hard cap (default 10_000): ERROR + drop OLDEST.
- SIGTERM/SIGINT install handler that sets stopping=True; run() final-flushes on exit
- Malformed lines log WARNING (raw bytes, rate-limited to 10/min); loop continues
- Blank lines (firmware emits \\n\\n between events) are silently skipped — they
  are normal protocol punctuation, NOT malformed content (per 02-01 capture)
- ts = int(time.time()) — wall-clock epoch seconds, no datetime module
- device_id (8th CSV field) logged ONCE at INFO on first event; re-logged only
  if it changes (sign of device swap)
- All log output is structlog JSON via observatory.logging.configure_logging
"""

from __future__ import annotations

import signal
import sqlite3
import time
from types import FrameType
from typing import Final

import sdnotify
import serial
import structlog

from observatory.db.connection import get_write_conn
from observatory.muon.parser import ParseError, parse_line

log = structlog.get_logger(__name__)

INSERT_SQL: Final[str] = (
    "INSERT INTO muon_events (ts, detector_pressure_hpa, detector_temp_c, amplitude, coincidence) "
    "VALUES (?, ?, ?, ?, ?)"
)

# Rate limit for malformed-line WARNING: at most 10 per rolling 60s window
PARSE_WARN_MAX_PER_WINDOW: Final[int] = 10
PARSE_WARN_WINDOW_SEC: Final[float] = 60.0

# sd_notify watchdog ping cadence (CONTEXT.md: 3x safety margin vs WatchdogSec=30s).
# Tests monkeypatch this constant down to <2s to exercise ping behaviour quickly.
WATCHDOG_PING_INTERVAL_SEC: int = 10

# In-process reopen backoff sequence (CONTEXT.md verbatim):
#   "1s, 2s, 5s, 10s, then 30s and loop"
# Trigger conditions (CONTEXT.md verbatim):
#   "60s of consecutive empty/silent reads, serial.SerialException, OSError on read"
# Worst-case time to recover from a glitch is therefore well under the
# WatchdogSec=30s budget after the first successful reopen — only catastrophic
# repeated failures escalate to systemd-driven process restart.
BACKOFF_SEQUENCE_SEC: Final[tuple[int, ...]] = (1, 2, 5, 10, 30)

# Per-readline timeout. Tests monkeypatch this down so silence_limit computes
# to ~2 empty reads in a few seconds instead of the production 60s.
SERIAL_READ_TIMEOUT_SEC: int = 5


class Reader:
    """Long-running PicoMuon serial → SQLite ingest loop.

    Public API:
        reader = Reader(port_path="/dev/picomuon", db_path="/var/lib/observatory/observatory.db")
        reader.run()         # blocks; returns when self.stopping is True

    For test usage: tests run reader.run() on a daemon thread (signal handlers
    cannot install off the main thread — that path is silently skipped) and
    drive shutdown by setting `reader.stopping = True` directly.
    """

    def __init__(
        self,
        port_path: str,
        db_path: str,
        flush_interval_sec: int = 5,
        buffer_max: int = 500,
        hard_cap: int = 10000,
        silence_timeout_sec: int = 60,
        notifier: sdnotify.SystemdNotifier | None = None,
    ) -> None:
        self.port_path = port_path
        self.db_path = db_path
        self.flush_interval_sec = flush_interval_sec
        self.buffer_max = buffer_max
        self.hard_cap = hard_cap
        self.silence_timeout_sec = silence_timeout_sec
        # Set by _read_session whenever a non-empty read happens; run() uses it
        # to decide whether to reset the backoff attempt counter after a session
        # returns (silence path) or raises (serial error path).
        self._had_successful_read: bool = False

        # (ts, pressure_hpa, temp_c, amplitude, coincidence)
        self.buffer: list[tuple[int, float | None, float | None, float, int]] = []
        self.last_bmp280: tuple[float | None, float | None] = (None, None)
        self.stopping: bool = False

        # Rate-limit bookkeeping for malformed-line WARNINGs
        self._parse_warn_window_start: float = time.monotonic()
        self._parse_warn_count: int = 0

        # Device metadata: log once on first event, again only if it changes
        self._last_device_id: str | None = None

        # sd_notify wiring. SystemdNotifier.notify() is a no-op if $NOTIFY_SOCKET
        # is unset, so the default works fine outside systemd (tests, dev).
        self._notifier = notifier if notifier is not None else sdnotify.SystemdNotifier()
        # Liveness tracking: ping watchdog only if a successful read OR flush
        # happened since the last ping (catches phantom uptime).
        now = time.monotonic()
        self._last_data_event: float = now
        self._last_watchdog_ping: float = now

    # ------------------------------------------------------------------ run

    def run(self) -> None:
        """Install signal handlers (if on main thread), then loop forever
        wrapping _read_session in a reopen/backoff cycle. Returns only on
        stopping=True or on a truly unexpected exception (which propagates
        so systemd's Restart=on-failure takes over)."""
        try:
            signal.signal(signal.SIGTERM, self._on_sigterm)
            signal.signal(signal.SIGINT, self._on_sigterm)
        except ValueError:
            # Not on main thread (test contexts). Rely on stopping attribute.
            pass

        attempt = 0  # index into BACKOFF_SEQUENCE_SEC
        try:
            while not self.stopping:
                self._had_successful_read = False
                try:
                    self._read_session()
                    # Returned (not raised) means the silence threshold fired.
                    # Backoff still applies, but the WARNING flavour differs.
                    if self.stopping:
                        break
                    log.warning("reopening_after_silence")
                except (serial.SerialException, OSError) as exc:
                    log.warning("serial_error", error=str(exc), attempt=attempt + 1)
                except Exception as exc:
                    # Anything else is genuinely unexpected; escalate to systemd.
                    log.error("unexpected_error", error=str(exc))
                    raise

                if self.stopping:
                    break

                # Successful read since last (re)open => reset backoff. The
                # one-off glitch shouldn't slow recovery from later glitches.
                if self._had_successful_read:
                    attempt = 0

                wait = BACKOFF_SEQUENCE_SEC[min(attempt, len(BACKOFF_SEQUENCE_SEC) - 1)]
                time.sleep(wait)
                # RESEARCH.md open question 4: avoid the exclusive=True flock
                # release race between close() and the next open().
                time.sleep(0.2)
                attempt += 1
                log.info("reopen_attempt", attempt=attempt)
        finally:
            self._final_flush()

    def _on_sigterm(self, signum: int, frame: FrameType | None) -> None:
        # STOPPING=1 MUST be sent before _final_flush runs so systemd's
        # accounting reflects the orderly shutdown (CONTEXT.md).
        self._notifier.notify("STOPPING=1")
        log.info("stopping", signum=signum)
        self.stopping = True

    # -------------------------------------------------------- watchdog ping

    def _maybe_ping_watchdog(self, now: float) -> None:
        """Ping systemd watchdog if interval elapsed AND a data event happened since."""
        if (now - self._last_watchdog_ping) >= WATCHDOG_PING_INTERVAL_SEC and (
            self._last_data_event >= self._last_watchdog_ping
        ):
            self._notifier.notify("WATCHDOG=1")
            self._last_watchdog_ping = now

    # -------------------------------------------------------- read session

    def _read_session(self) -> None:
        """One open→read→close cycle. RETURNS normally when the silence
        threshold is exceeded (run() will back off + reopen). PROPAGATES
        serial.SerialException / OSError to run() for the same backoff path.
        ParseError stays in-loop via _handle_line + _handle_parse_error."""
        consecutive_empty = 0
        # silence_limit = how many consecutive empty readlines == silence_timeout.
        # readline() returns b"" after each timeout=SERIAL_READ_TIMEOUT_SEC expiry.
        silence_limit = max(1, self.silence_timeout_sec // max(1, SERIAL_READ_TIMEOUT_SEC))

        with serial.Serial(
            self.port_path,
            baudrate=115200,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=SERIAL_READ_TIMEOUT_SEC,
            exclusive=True,
        ) as ser:
            # First read is always discarded — avoids a guaranteed mid-event
            # partial on service start. On reopen this runs again, which is the
            # correct behaviour (a reconnected device may also emit a partial).
            ser.readline()

            # Port is open + first-line discarded => signal systemd we are READY.
            # READY=1 is idempotent in systemd; re-sending on reopen is harmless.
            self._notifier.notify("READY=1")
            self._last_data_event = time.monotonic()
            log.info("ready", port_path=self.port_path)

            last_flush = time.monotonic()
            while not self.stopping:
                line = ser.readline()
                now = time.monotonic()
                if line:
                    consecutive_empty = 0
                    # Non-empty: blank lines (b"\n") are silently skipped inside
                    # _handle_line. The buffer/cache update + liveness write
                    # happen there too. Mark that the session has seen real I/O.
                    if line.strip():
                        self._had_successful_read = True
                    self._handle_line(line)
                else:
                    consecutive_empty += 1
                    if consecutive_empty >= silence_limit:
                        log.warning(
                            "serial_silence_reopen",
                            seconds=consecutive_empty * SERIAL_READ_TIMEOUT_SEC,
                        )
                        return  # falls through to backoff in run()
                if (
                    now - last_flush >= self.flush_interval_sec
                    or len(self.buffer) >= self.buffer_max
                ):
                    self._flush()
                    last_flush = now
                self._maybe_ping_watchdog(now)

    # ------------------------------------------------------- line handling

    def _handle_line(self, line: bytes) -> None:
        # Blank-line tolerance: firmware emits \n\n between every event. These
        # are normal protocol punctuation, NOT malformed content. Silently
        # skip without incrementing the malformed counter or logging WARNING.
        if not line.strip():
            return

        try:
            ev = parse_line(line)
        except ParseError as exc:
            self._handle_parse_error(line, exc)
            return

        # Update BMP280 cache from the event (per-event protocol confirmed by
        # 02-01 capture; cache defends against any future partial-line firmware).
        self.last_bmp280 = (ev.detector_pressure_hpa, ev.detector_temp_c)

        # Log device metadata once per port-open, and again only if it changes.
        if ev.device_id is not None and ev.device_id != self._last_device_id:
            log.info("muon_device_metadata", device_id=ev.device_id)
            self._last_device_id = ev.device_id

        self.buffer.append(
            (
                int(time.time()),
                self.last_bmp280[0],
                self.last_bmp280[1],
                float(ev.amplitude),
                ev.coincidence,
            )
        )
        # Successful parse + buffer append => data is moving through the pipeline.
        self._last_data_event = time.monotonic()

    def _handle_parse_error(self, line: bytes, exc: ParseError) -> None:
        now = time.monotonic()
        if now - self._parse_warn_window_start >= PARSE_WARN_WINDOW_SEC:
            self._parse_warn_window_start = now
            self._parse_warn_count = 0
        if self._parse_warn_count < PARSE_WARN_MAX_PER_WINDOW:
            log.warning("parse_error", raw=line[:200], error=str(exc))
            self._parse_warn_count += 1

    # --------------------------------------------------------------- flush

    def _flush(self) -> None:
        if not self.buffer:
            # Empty flushes count as alive: the periodic flush attempt itself
            # proves the loop is ticking and (when there's no contention) the
            # DB connection is healthy. Update liveness so the watchdog can
            # ping during quiet stretches.
            self._last_data_event = time.monotonic()
            return

        try:
            with get_write_conn(self.db_path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.executemany(INSERT_SQL, self.buffer)
                conn.execute("COMMIT")
            log.info("flush", batch_size=len(self.buffer))
            self.buffer.clear()
            # Successful DB flush => pipeline is healthy.
            self._last_data_event = time.monotonic()
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower():
                log.warning("database_locked_retry_next_tick", buffered=len(self.buffer))
                # Retain buffer; only drop OLDEST if we exceed the hard cap.
                if len(self.buffer) > self.hard_cap:
                    dropped = len(self.buffer) - self.hard_cap
                    self.buffer = self.buffer[-self.hard_cap :]
                    log.error("buffer_overflow_dropping_oldest", dropped=dropped)
            else:
                raise

    def _final_flush(self) -> None:
        try:
            self._flush()
        except Exception as exc:
            log.error("final_flush_failed", error=str(exc), buffered=len(self.buffer))
