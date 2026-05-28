"""RED placeholder — Plan 08-06 implements cadence_warning helper.

Locked test names so the downstream plan can fill bodies without inventing
file paths or marker conventions.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="RED — Plan 08-06 implements cadence_warning helper")
def test_cadence_warning_overdue_weather() -> None:
    pass


@pytest.mark.skip(reason="RED — Plan 08-06 implements cadence_warning helper")
def test_cadence_warning_fresh_returns_false() -> None:
    pass
