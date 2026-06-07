"""NMDB / NEST neutron-monitor poller — systemd oneshot entry point (Phase 13, MU2-06).

Wave-0 RED skeleton: ``main`` raises NotImplementedError; Wave 3 (plan 13-04)
implements the composition (one hardened ``_http.fetch`` -> ``parse_nmdb`` ->
append-window ``write_nmdb`` -> always emit one ``poller_runs`` audit row).

``fetch`` / ``configure_logging`` / ``settings`` are imported by name so the
test harness can monkeypatch them (the poller-conftest rebind loops register this
module) exactly as for the airquality/forecast pollers. No ``Restart=`` in the
systemd unit — the hourly timer IS the retry (STATE 04-05).
"""

from __future__ import annotations

import structlog

from observatory.config import settings
from observatory.logging import configure_logging
from observatory.pollers._http import (
    CrossHostRedirect,
    ResponseTooLarge,
    RetriesExhausted,
    fetch,
)
from observatory.pollers._write import write_nmdb
from observatory.pollers.nmdb.parser import parse_nmdb

log = structlog.get_logger(__name__)
SOURCE = "nmdb"

__all__ = [
    "CrossHostRedirect",
    "ResponseTooLarge",
    "RetriesExhausted",
    "configure_logging",
    "fetch",
    "main",
    "parse_nmdb",
    "settings",
    "write_nmdb",
]


def main() -> int:
    """Run one NMDB poll. Implemented in Wave 3 (plan 13-04)."""
    raise NotImplementedError("nmdb poller main() is implemented in Wave 3 (plan 13-04)")


if __name__ == "__main__":
    raise SystemExit(main())
