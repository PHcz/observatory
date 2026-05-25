"""Unit tests for observatory.muon.__main__: NTP gate + main() ordering.

Covers:
- OFFSET_RE parses chronyc tracking 'System time' line (positive/negative/no match)
- wait_for_ntp() returns when offset < threshold within timeout
- wait_for_ntp() raises SystemExit after timeout if still skewed
- wait_for_ntp() tolerates chronyc invocation failure (returncode != 0)
- subprocess.run is invoked with timeout=5
- main() orders configure_logging -> wait_for_ntp -> Reader.run

All tests mock subprocess.run on the observatory.muon.__main__ module so no
real chronyc binary is touched.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from observatory.muon import __main__ as muon_main
from observatory.muon.__main__ import OFFSET_RE, wait_for_ntp

GOOD_STDOUT = (
    "Reference ID    : C0A80001 (router.lan)\n"
    "Stratum         : 3\n"
    "System time     : 0.000006523 seconds slow of NTP time\n"
)

BAD_STDOUT = (
    "Reference ID    : 7F7F0101 ()\n"
    "Stratum         : 10\n"
    "System time     : 1.500000000 seconds slow of NTP time\n"
)


def _ok_completed(stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["chronyc", "tracking"], returncode=0, stdout=stdout, stderr=""
    )


def _fail_completed() -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["chronyc", "tracking"], returncode=1, stdout="", stderr="error"
    )


# ---------------------------------------------------------------- regex tests


def test_offset_regex_parses_typical_chronyc_output() -> None:
    line = "System time     : 0.000006523 seconds slow of NTP time"
    m = OFFSET_RE.search(line)
    assert m is not None
    assert m.group(1) == "0.000006523"


def test_offset_regex_parses_negative_offset() -> None:
    line = "System time     : -0.123 seconds fast of NTP time"
    m = OFFSET_RE.search(line)
    assert m is not None
    assert m.group(1) == "-0.123"


def test_offset_regex_parses_no_match() -> None:
    assert OFFSET_RE.search("nothing relevant here") is None


# -------------------------------------------------------------- gate behaviour


def test_ntp_gate_returns_when_offset_within_threshold() -> None:
    with patch.object(
        muon_main.subprocess, "run", return_value=_ok_completed(GOOD_STDOUT)
    ) as m_run:
        # Should return None quickly
        result = wait_for_ntp(max_seconds=30)
        assert result is None
        assert m_run.called


def test_ntp_gate_times_out_and_raises() -> None:
    with patch.object(muon_main.subprocess, "run", return_value=_ok_completed(BAD_STDOUT)):
        with pytest.raises(SystemExit) as excinfo:
            wait_for_ntp(max_seconds=2)
        assert "NTP gate failed" in str(excinfo.value)


def test_ntp_gate_handles_chronyc_failure() -> None:
    """chronyc returning non-zero must not crash; loop continues until timeout."""
    with patch.object(muon_main.subprocess, "run", return_value=_fail_completed()):
        with pytest.raises(SystemExit) as excinfo:
            wait_for_ntp(max_seconds=2)
        assert "NTP gate failed" in str(excinfo.value)


def test_ntp_gate_handles_chronyc_missing() -> None:
    """FileNotFoundError (chronyc not installed) must be tolerated, not crash."""
    with patch.object(muon_main.subprocess, "run", side_effect=FileNotFoundError("chronyc")):
        with pytest.raises(SystemExit):
            wait_for_ntp(max_seconds=2)


def test_ntp_gate_uses_5s_subprocess_timeout() -> None:
    with patch.object(
        muon_main.subprocess, "run", return_value=_ok_completed(GOOD_STDOUT)
    ) as m_run:
        wait_for_ntp(max_seconds=30)
    # Verify the first call used timeout=5
    kwargs = m_run.call_args.kwargs
    assert kwargs.get("timeout") == 5


# ---------------------------------------------------------- main() ordering


def test_main_orders_configure_logging_then_wait_for_ntp_then_reader() -> None:
    """configure_logging must run BEFORE wait_for_ntp, which runs BEFORE Reader.run."""
    tracker = MagicMock()
    fake_reader_instance = MagicMock()
    tracker.attach_mock(fake_reader_instance.run, "reader_run")

    def fake_configure() -> None:
        tracker.configure_logging()

    def fake_wait(*a: object, **kw: object) -> None:
        tracker.wait_for_ntp()

    def fake_reader_factory(*a: object, **kw: object) -> MagicMock:
        tracker.reader_init()
        return fake_reader_instance

    with (
        patch.object(muon_main, "configure_logging", side_effect=fake_configure),
        patch.object(muon_main, "wait_for_ntp", side_effect=fake_wait),
        patch.object(muon_main, "Reader", side_effect=fake_reader_factory),
    ):
        muon_main.main()

    call_names = [c[0] for c in tracker.mock_calls]
    # Filter to just the events we care about (skip nested mock_call entries)
    relevant = [
        n
        for n in call_names
        if n in ("configure_logging", "wait_for_ntp", "reader_init", "reader_run")
    ]
    assert relevant == ["configure_logging", "wait_for_ntp", "reader_init", "reader_run"], (
        f"Wrong call order: {relevant}"
    )
