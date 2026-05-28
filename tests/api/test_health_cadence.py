"""RED placeholder — Plan 08-06 wires cadence_warning field onto /api/health.

Locks the test file name + skipped placeholder for downstream extension.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="RED — Plan 08-06 wires cadence_warning onto /api/health")
def test_health_endpoint_emits_cadence_warning_per_source() -> None:
    pass
