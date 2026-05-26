"""Entry point: ``python -m observatory.pollers.blitzortung``.

Long-running Type=notify service. configure_logging fires once; SIGTERM/SIGINT
flip ``client.stopping`` so the run loop tears down cleanly.

NTP gate intentionally NOT enforced here — strike timestamps come from the
Blitzortung server (encoded in each frame), not our local clock, so a small
local drift does not corrupt the data. The systemd unit still orders after
``time-sync.target`` for general hygiene.
"""

from __future__ import annotations

import signal
import sys
from types import FrameType

import structlog

from observatory.logging import configure_logging
from observatory.pollers.blitzortung.client import BlitzortungClient

log = structlog.get_logger(__name__)


def main() -> int:
    configure_logging()
    client = BlitzortungClient()

    def _on_term(signum: int, _frame: FrameType | None) -> None:
        log.info("blitz_stopping", signum=signum)
        client.stopping = True

    try:
        signal.signal(signal.SIGTERM, _on_term)
        signal.signal(signal.SIGINT, _on_term)
    except ValueError:
        # Not on main thread (test contexts). Rely on stopping attribute.
        pass

    client.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
