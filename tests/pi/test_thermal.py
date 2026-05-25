"""Unit tests for observatory.pi.thermal (Plan 05-01).

All subprocess.run calls to vcgencmd are mocked via the `fake_vcgencmd`
fixture in tests/pi/conftest.py — these tests run without a real vcgencmd
binary present (dev Mac, CI).
"""

from __future__ import annotations

from typing import Any

import pytest

from observatory.config import settings
from observatory.pi.thermal import (
    ThermalReadError,
    ThermalWarningEmitter,
    derive_status,
    read_temp_c,
    read_throttled,
)

# ---------------------------------------------------------------------------
# read_temp_c
# ---------------------------------------------------------------------------


def test_read_temp_c_happy_path(fake_vcgencmd: Any) -> None:
    fake_vcgencmd("measure_temp", "temp=42.1'C\n")
    assert read_temp_c() == 42.1
    # Ensure we invoked the vcgencmd binary with the right subcommand
    assert fake_vcgencmd.calls, "expected subprocess.run to be called"
    args = fake_vcgencmd.calls[-1]
    assert args[-1] == "measure_temp"
    assert args[0] == settings.pi_vcgencmd_path


def test_read_temp_c_non_zero_exit_raises(fake_vcgencmd: Any) -> None:
    fake_vcgencmd("measure_temp", stdout="", returncode=2, stderr="VCHI initialization failed")
    with pytest.raises(ThermalReadError) as exc_info:
        read_temp_c()
    msg = str(exc_info.value)
    assert "exit=2" in msg
    assert "VCHI initialization failed" in msg


def test_read_temp_c_unparseable_stdout_raises(fake_vcgencmd: Any) -> None:
    fake_vcgencmd("measure_temp", stdout="oops\n")
    with pytest.raises(ThermalReadError) as exc_info:
        read_temp_c()
    assert "unparseable" in str(exc_info.value)
    assert "oops" in str(exc_info.value)


# ---------------------------------------------------------------------------
# read_throttled
# ---------------------------------------------------------------------------


def test_read_throttled_happy_path_zero(fake_vcgencmd: Any) -> None:
    fake_vcgencmd("get_throttled", "throttled=0x0\n")
    assert read_throttled() == "0x0"


def test_read_throttled_non_zero_bits(fake_vcgencmd: Any) -> None:
    fake_vcgencmd("get_throttled", "throttled=0x50000\n")
    assert read_throttled() == "0x50000"


def test_read_throttled_non_zero_exit_raises(fake_vcgencmd: Any) -> None:
    fake_vcgencmd("get_throttled", stdout="", returncode=1, stderr="boom")
    with pytest.raises(ThermalReadError) as exc_info:
        read_throttled()
    assert "exit=1" in str(exc_info.value)


def test_read_throttled_unparseable_raises(fake_vcgencmd: Any) -> None:
    fake_vcgencmd("get_throttled", stdout="garbage\n")
    with pytest.raises(ThermalReadError) as exc_info:
        read_throttled()
    assert "unparseable" in str(exc_info.value)


# ---------------------------------------------------------------------------
# derive_status
# ---------------------------------------------------------------------------


def test_derive_status_healthy() -> None:
    status, warnings = derive_status(42.1, "0x0")
    assert status == "healthy"
    assert warnings == []


def test_derive_status_warning_temp_only() -> None:
    status, warnings = derive_status(75.0, "0x0")
    assert status == "warning"
    assert warnings == ["pi_temp_high"]


def test_derive_status_warning_throttled_only() -> None:
    status, warnings = derive_status(50.0, "0x50000")
    assert status == "warning"
    assert warnings == ["pi_throttled"]


def test_derive_status_warning_both() -> None:
    status, warnings = derive_status(75.0, "0x50000")
    assert status == "warning"
    assert warnings == ["pi_temp_high", "pi_throttled"]


def test_derive_status_critical_temp_alone() -> None:
    status, warnings = derive_status(82.0, "0x0")
    assert status == "critical"
    assert warnings == ["pi_temp_critical"]


def test_derive_status_critical_supersedes_throttled() -> None:
    status, warnings = derive_status(85.0, "0x50000")
    assert status == "critical"
    # Critical supersedes — single warning, no pi_throttled / pi_temp_high mix
    assert warnings == ["pi_temp_critical"]


def test_derive_status_honors_monkeypatched_warning_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pi_temp_warning_c", 60.0)
    status, warnings = derive_status(65.0, "0x0")
    assert status == "warning"
    assert warnings == ["pi_temp_high"]


# ---------------------------------------------------------------------------
# ThermalWarningEmitter
# ---------------------------------------------------------------------------


class FakeClock:
    """Manually-advanced clock for ThermalWarningEmitter tests."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_emitter_first_observation_healthy_returns_empty() -> None:
    clock = FakeClock()
    emitter = ThermalWarningEmitter(rate_limit_sec=600, clock=clock)
    assert emitter.observe("healthy", []) == []


def test_emitter_transition_healthy_to_warning_emits_all() -> None:
    clock = FakeClock()
    emitter = ThermalWarningEmitter(rate_limit_sec=600, clock=clock)
    emitter.observe("healthy", [])
    out = emitter.observe("warning", ["pi_temp_high", "pi_throttled"])
    assert out == ["pi_temp_high", "pi_throttled"]


def test_emitter_same_state_within_rate_limit_returns_empty() -> None:
    clock = FakeClock()
    emitter = ThermalWarningEmitter(rate_limit_sec=600, clock=clock)
    emitter.observe("warning", ["pi_temp_high"])  # first emit
    clock.advance(60)  # < rate_limit
    out = emitter.observe("warning", ["pi_temp_high"])
    assert out == []


def test_emitter_same_state_past_rate_limit_re_emits() -> None:
    clock = FakeClock()
    emitter = ThermalWarningEmitter(rate_limit_sec=600, clock=clock)
    emitter.observe("warning", ["pi_temp_high"])
    clock.advance(600)  # exactly at rate_limit boundary -> re-emit
    out = emitter.observe("warning", ["pi_temp_high"])
    assert out == ["pi_temp_high"]


def test_emitter_transition_warning_to_critical_emits_new() -> None:
    clock = FakeClock()
    emitter = ThermalWarningEmitter(rate_limit_sec=600, clock=clock)
    emitter.observe("warning", ["pi_temp_high"])
    clock.advance(10)
    out = emitter.observe("critical", ["pi_temp_critical"])
    assert out == ["pi_temp_critical"]
