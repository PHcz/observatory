"""Pi thermal monitoring via vcgencmd. Output consumed by /api/health (Plan 05-05).

All metrics + thresholds locked in 05-CONTEXT.md §"Pi thermal monitoring":

- ``temp_c`` from ``vcgencmd measure_temp`` (float)
- ``throttled`` raw hex from ``vcgencmd get_throttled`` (string)
- Status: ``healthy`` < 70°C AND throttled==0x0; ``warning`` if 70<=temp<80 OR
  throttled!=0x0; ``critical`` if temp>=80 (critical supersedes throttled).
- Warning emission rate-limited via ``ThermalWarningEmitter``: first crossing +
  every ``rate_limit_sec`` (default 600s) while in the warning/critical state.

Subprocess invocations whitelist bandit B404/B603/B607 — argv is fixed (no shell,
no user input), and ``vcgencmd`` is installed system-wide on Pi OS.
"""

from __future__ import annotations

import re
import subprocess
import time
from collections.abc import Callable
from typing import Literal

import structlog

from observatory.config import settings

log = structlog.get_logger(__name__)

_TEMP_RE = re.compile(r"^temp=([\d.]+)'C\s*$")
_THROTTLED_RE = re.compile(r"^throttled=(0x[\da-fA-F]+)\s*$")
_SUBPROCESS_TIMEOUT_SEC = 5

PiStatus = Literal["healthy", "warning", "critical"]


class ThermalReadError(RuntimeError):
    """vcgencmd failed (non-zero exit) or its stdout was unparseable."""


def _binary() -> str:
    return settings.pi_vcgencmd_path


def read_temp_c(binary: str | None = None) -> float:
    """Return current SoC temperature in °C parsed from ``vcgencmd measure_temp``."""
    b = binary or _binary()
    proc = subprocess.run(
        [b, "measure_temp"],
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT_SEC,
        check=False,
    )
    if proc.returncode != 0:
        raise ThermalReadError(
            f"vcgencmd measure_temp exit={proc.returncode}: {proc.stderr!r}"
        )
    m = _TEMP_RE.match(proc.stdout.strip())
    if not m:
        raise ThermalReadError(f"unparseable measure_temp output: {proc.stdout!r}")
    return float(m.group(1))


def read_throttled(binary: str | None = None) -> str:
    """Return the raw throttled hex string from ``vcgencmd get_throttled``.

    ``0x0`` means healthy; non-zero values pack the currently-and-historically
    throttled bit flags (see ``man vcgencmd`` for the bit layout).
    """
    b = binary or _binary()
    proc = subprocess.run(
        [b, "get_throttled"],
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT_SEC,
        check=False,
    )
    if proc.returncode != 0:
        raise ThermalReadError(
            f"vcgencmd get_throttled exit={proc.returncode}: {proc.stderr!r}"
        )
    m = _THROTTLED_RE.match(proc.stdout.strip())
    if not m:
        raise ThermalReadError(f"unparseable get_throttled output: {proc.stdout!r}")
    return m.group(1)


def derive_status(temp_c: float, throttled_hex: str) -> tuple[PiStatus, list[str]]:
    """Map raw thermal readings to a ``(status, warnings)`` tuple.

    Thresholds honour ``settings.pi_temp_warning_c`` and
    ``settings.pi_temp_critical_c`` so tests can monkeypatch.

    ``critical`` supersedes other warnings — when the SoC is at/over the
    critical threshold the operator's response is the same regardless of
    throttle bits, so we only surface ``pi_temp_critical``.
    """
    if temp_c >= settings.pi_temp_critical_c:
        return ("critical", ["pi_temp_critical"])
    warnings: list[str] = []
    if temp_c >= settings.pi_temp_warning_c:
        warnings.append("pi_temp_high")
    if int(throttled_hex, 16) != 0:
        warnings.append("pi_throttled")
    status: PiStatus = "warning" if warnings else "healthy"
    return (status, warnings)


class ThermalWarningEmitter:
    """Stateful transition detector for rate-limited warning emission.

    Per 05-CONTEXT §"Pi thermal monitoring": "log first crossing + every 10
    minutes thereafter while in the warning/critical state, NOT every
    health-check poll".

    Usage from ``/api/health`` (Plan 05-05)::

        emitter = ThermalWarningEmitter()  # module-level
        status, warnings = derive_status(temp_c, throttled_hex)
        for w in emitter.observe(status, warnings):
            log.warning(w, status=status, temp_c=temp_c, throttled=throttled_hex)

    The clock is injectable for deterministic tests.
    """

    def __init__(
        self,
        rate_limit_sec: int | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._rate_limit: float = (
            rate_limit_sec
            if rate_limit_sec is not None
            else settings.pi_thermal_warning_rate_limit_sec
        )
        self._clock = clock
        self._last_status: PiStatus | None = None
        self._last_emit_ts: dict[str, float] = {}

    def observe(self, status: PiStatus, warnings: list[str]) -> list[str]:
        """Return the subset of ``warnings`` that should be logged this tick.

        - Transition into a new status → emit ALL active warnings.
        - Same status as last tick → emit any warning brand-new or whose last
          emit timestamp is at least ``rate_limit_sec`` ago.
        - Returns ``[]`` when nothing should be emitted.
        """
        now = self._clock()
        transition = self._last_status != status
        to_emit: list[str] = []
        for w in warnings:
            last = self._last_emit_ts.get(w)
            if transition or last is None or (now - last) >= self._rate_limit:
                to_emit.append(w)
                self._last_emit_ts[w] = now
        self._last_status = status
        return to_emit
