"""Service entrypoint: python -m observatory.muon.

Order of operations (CONTEXT.md — must not reorder):
  1. configure_logging() — structlog JSON to stdout, journald collects
  2. wait_for_ntp() — block up to MUON_NTP_GATE_TIMEOUT_SEC for chronyc convergence
  3. Reader(...).run() — blocking ingest loop until SIGTERM

The NTP gate prevents the worst muon-data pitfall: silently writing skewed
event timestamps before chrony has converged at boot. If chronyc reports an
offset >= 0.5s after MUON_NTP_GATE_TIMEOUT_SEC (default 30s), the process
exits non-zero and systemd's Restart=on-failure takes over.

The OFFSET_RE regex is quoted verbatim from 02-RESEARCH.md Pattern 3. Do not
reformulate it without updating the research note.
"""

from __future__ import annotations

import re
import subprocess
import time

import structlog

from observatory.config import settings
from observatory.logging import configure_logging
from observatory.muon.reader import Reader

OFFSET_RE = re.compile(r"System time\s*:\s*([-+]?[\d.]+)\s+seconds")
NTP_THRESHOLD_SECONDS = 0.5

log = structlog.get_logger(__name__)


def wait_for_ntp(
    max_seconds: int | None = None,
    threshold_s: float = NTP_THRESHOLD_SECONDS,
) -> None:
    """Block until `chronyc tracking` reports offset < threshold_s, or raise SystemExit.

    Polls every ~1s, with a 5s subprocess timeout per chronyc invocation. Tolerates
    transient chronyc failures (non-zero exit, TimeoutExpired) and FileNotFoundError
    (chronyc not installed) by sleeping and retrying until the overall deadline.
    """
    if max_seconds is None:
        max_seconds = settings.muon_ntp_gate_timeout_sec
    deadline = time.monotonic() + max_seconds
    last_offset: float | None = None
    while time.monotonic() < deadline:
        try:
            result = subprocess.run(
                ["chronyc", "tracking"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            log.warning("chronyc_invocation_failed", error=str(exc))
            time.sleep(1)
            continue

        if result.returncode != 0:
            log.warning("chronyc_returned_nonzero", returncode=result.returncode)
            time.sleep(1)
            continue

        match = OFFSET_RE.search(result.stdout)
        if match:
            offset = float(match.group(1))
            last_offset = offset
            if abs(offset) < threshold_s:
                log.info("ntp_gate_passed", offset_seconds=offset)
                return
            log.info("ntp_gate_waiting", offset_seconds=offset, threshold_s=threshold_s)
        time.sleep(1)

    raise SystemExit(
        f"NTP gate failed: chronyc offset still >= {threshold_s}s after {max_seconds}s "
        f"(last_offset={last_offset})"
    )


def main() -> None:
    configure_logging()
    log.info("starting", port_path=settings.muon_serial_path)
    wait_for_ntp()
    reader = Reader(
        port_path=settings.muon_serial_path,
        db_path=settings.observatory_db_path,
        flush_interval_sec=settings.muon_flush_interval_sec,
        buffer_max=settings.muon_buffer_max,
    )
    reader.run()


if __name__ == "__main__":
    main()
