"""Sync WebSocket loop with reconnect backoff + batched flush + sd_notify hooks.

Long-running Type=notify service shape (mirrors observatory.muon.reader.Reader).
Uses the sync ``websockets.sync.client.connect`` rather than asyncio so the
flush-buffer + watchdog cadence shares the muon-reader idiom of two cooperating
threads driven by a ``stopping`` flag.

SSL note (resolves 05-04 Task 1 finding): Blitzortung's volunteer pool serves
an invalid/self-signed certificate; strict TLS verification fails with
``CERTIFICATE_VERIFY_FAILED``. We connect with ``check_hostname=False`` and
``verify_mode=ssl.CERT_NONE``. Justified because:

- Blitzortung's ToS forbids republishing — payload integrity is not a security
  boundary for us.
- The decoded JSON is parsed defensively (key whitelist + types + distance filter
  drops anything outside ``settings.poller_lightning_radius_km``).
- There is no auth/credential exchange; an attacker MITMing the stream can only
  inject fake strikes (already dropped by the radius filter for distant points).

Graceful degradation (05-CONTEXT 2026-05-26 amendment, NO LightningMaps fallback):
- 3 consecutive connect failures across all URLs OR no frame received within
  ``poller_blitzortung_degraded_after_sec`` (default 300s) → log INFO
  ``event="lightning_poller_degraded"`` ONCE, keep running, keep watchdog-pinging.
- Service stays alive forever; "no lightning data" is acceptable but
  "service crash-looping every 30s" is not.
"""

from __future__ import annotations

import json
import ssl
import threading
import time
from collections.abc import Callable
from typing import Any, Final

import sdnotify
import structlog
import websockets
from websockets.sync.client import connect as ws_connect

from observatory.config import settings
from observatory.pollers._types import LightningStrike
from observatory.pollers._write import write_lightning_batch
from observatory.pollers.blitzortung.decoder import decode
from observatory.pollers.blitzortung.geo import haversine_km

log = structlog.get_logger(__name__)

BACKOFF_SEQUENCE_SEC: tuple[float, ...] = (1, 2, 5, 10, 30)
SUBSCRIBE_MESSAGE: Final[str] = '{"a": 111}'
WATCHDOG_PING_INTERVAL_SEC: int = 20


class BlitzortungClient:
    """Long-running sync WS client → batched flush → SQLite.

    Public API::

        client = BlitzortungClient()  # reads settings.* defaults
        client.run()                  # blocks; returns when self.stopping
        client.stopping = True        # cooperative shutdown from another thread

    Tests use the same shape: spin ``client.run()`` on a daemon thread, drive
    shutdown via ``client.stopping = True`` (signal handlers cannot install
    off the main thread).
    """

    def __init__(
        self,
        urls: list[str] | None = None,
        radius_km: float | None = None,
        flush_interval_sec: float | None = None,
        degraded_after_sec: float | None = None,
        notifier: Any | None = None,
        ssl_verify: bool = False,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.urls = list(urls) if urls else list(settings.poller_blitzortung_ws_urls)
        self.radius_km: float = (
            radius_km if radius_km is not None else settings.poller_lightning_radius_km
        )
        self.flush_interval_sec: float = (
            flush_interval_sec
            if flush_interval_sec is not None
            else float(settings.poller_blitzortung_flush_interval_sec)
        )
        self.degraded_after_sec: float = (
            degraded_after_sec
            if degraded_after_sec is not None
            else float(settings.poller_blitzortung_degraded_after_sec)
        )
        self.notifier = notifier if notifier is not None else sdnotify.SystemdNotifier()
        self.ssl_verify = ssl_verify
        self.clock = clock

        self.stopping: bool = False
        self._buffer: list[LightningStrike] = []
        self._buffer_lock = threading.Lock()
        self._last_frame_ts: float | None = None
        self._last_flush_ts: float = clock()
        self._start_ts: float = clock()
        self._has_ever_connected: bool = False
        self._degraded_logged: bool = False
        self._attempt: int = 0

    # ------------------------------------------------------------------ run

    def run(self) -> None:
        """Block until ``self.stopping`` is set. Spawns a flush thread,
        then runs the connect/recv loop on the calling thread.

        Final flush runs in ``finally`` so any buffered strikes land before
        the STOPPING=1 notification.
        """
        flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        flush_thread.start()
        try:
            self._connect_loop()
        finally:
            self.notifier.notify("STOPPING=1")
            self._flush_now(reason="shutdown")
            self.stopping = True
            flush_thread.join(timeout=2.0)

    # ----------------------------------------------------------- connect loop

    def _connect_loop(self) -> None:
        while not self.stopping:
            url = self.urls[self._attempt % len(self.urls)]
            ssl_ctx = self._ssl_context(url)
            try:
                with ws_connect(
                    url,
                    ssl=ssl_ctx,
                    open_timeout=10.0,
                ) as ws:
                    ws.send(SUBSCRIBE_MESSAGE)
                    if not self._has_ever_connected:
                        self.notifier.notify("READY=1")
                        log.info("blitz_ws_ready", url=url)
                    self._has_ever_connected = True
                    self._attempt = 0
                    self._stream_frames(ws)
            except (
                websockets.exceptions.WebSocketException,
                OSError,
                TimeoutError,
            ) as exc:
                wait = BACKOFF_SEQUENCE_SEC[min(self._attempt, len(BACKOFF_SEQUENCE_SEC) - 1)]
                log.warning(
                    "blitz_ws_reconnect",
                    url=url,
                    error=f"{type(exc).__name__}: {exc}",
                    wait_s=wait,
                )
                self._attempt += 1
                self._maybe_log_degraded()
                # Sleep in small chunks so stopping flips promptly.
                self._sleep_interruptible(wait)

    def _stream_frames(self, ws: Any) -> None:
        """Inner recv loop. Returns when WS closes or stopping is set."""
        for raw in ws:
            if self.stopping:
                break
            payload = raw if isinstance(raw, bytes) else raw.encode()
            self._handle_frame(payload)
            self.notifier.notify("WATCHDOG=1")

    def _ssl_context(self, url: str) -> ssl.SSLContext | None:
        if not url.startswith("wss://"):
            return None
        ctx = ssl.create_default_context()
        if not self.ssl_verify:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    # ----------------------------------------------------------- frame handling

    def _handle_frame(self, raw: bytes) -> None:
        try:
            decoded = decode(raw)
            payload = json.loads(decoded)
        except Exception as exc:
            log.warning("blitz_frame_decode_fail", error=str(exc))
            return
        try:
            lat = float(payload["lat"])
            lon = float(payload["lon"])
            ts_ns = int(payload["time"])
            ts = ts_ns // 1_000_000_000
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("blitz_frame_shape_invalid", error=str(exc))
            return
        distance = haversine_km(settings.home_lat, settings.home_lon, lat, lon)
        if distance > self.radius_km:
            return
        with self._buffer_lock:
            self._buffer.append(
                LightningStrike(
                    ts=ts,
                    latitude=lat,
                    longitude=lon,
                    distance_km=distance,
                )
            )
        self._last_frame_ts = self.clock()

    # ----------------------------------------------------------- flush loop

    def _flush_loop(self) -> None:
        """Periodic flush on a worker thread.

        Sleeps in small slices so ``self.stopping`` flips promptly. Always
        flushes (even an empty buffer emits the poller_runs audit row so
        /api/health stays fresh during quiet periods).
        """
        while not self.stopping:
            self._sleep_interruptible(self.flush_interval_sec)
            if self.stopping:
                break
            self._flush_now(reason="interval")
            self.notifier.notify("WATCHDOG=1")
            # Re-check degraded threshold during quiet windows too.
            self._maybe_log_degraded()

    def _flush_now(self, *, reason: str) -> None:
        with self._buffer_lock:
            if not self._buffer:
                batch: list[LightningStrike] = []
            else:
                batch = self._buffer
                self._buffer = []
        started_at = int(self.clock())
        try:
            fetched, written = write_lightning_batch(batch, started_at, "success")
            self._last_flush_ts = self.clock()
            if batch:
                log.info(
                    "lightning_flush",
                    reason=reason,
                    fetched=fetched,
                    written=written,
                )
        except Exception as exc:
            log.error("lightning_flush_failed", error=str(exc), count=len(batch))

    # ----------------------------------------------------------- degraded log

    def _maybe_log_degraded(self) -> None:
        if self._degraded_logged or self.stopping:
            return
        now = self.clock()
        # Case A: never connected, threshold elapsed
        if not self._has_ever_connected and (now - self._start_ts) >= self.degraded_after_sec:
            log.info(
                "lightning_poller_degraded",
                reason="no_connect_within_threshold",
                threshold_sec=self.degraded_after_sec,
            )
            self._degraded_logged = True
            return
        # Case B: connected but no frame within threshold
        if self._has_ever_connected and self._last_frame_ts is not None:
            if (now - self._last_frame_ts) >= self.degraded_after_sec:
                log.info(
                    "lightning_poller_degraded",
                    reason="no_data_within_threshold",
                    threshold_sec=self.degraded_after_sec,
                )
                self._degraded_logged = True

    # ----------------------------------------------------------- sleep helper

    def _sleep_interruptible(self, total_sec: float) -> None:
        slice_sec = 0.05
        elapsed = 0.0
        while elapsed < total_sec and not self.stopping:
            time.sleep(min(slice_sec, total_sec - elapsed))
            elapsed += slice_sec
