"""Shared Pi thermal test fixtures: subprocess mock for vcgencmd."""

from __future__ import annotations

import subprocess
from subprocess import CompletedProcess
from typing import Any

import pytest


@pytest.fixture
def fake_vcgencmd(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Replace subprocess.run with a configurable fake. Returns a setter callable.

    Usage:
        def test_x(fake_vcgencmd):
            fake_vcgencmd("measure_temp", "temp=55.6'C\\n")
            fake_vcgencmd("get_throttled", "throttled=0x0\\n")
            # call code under test, which invokes subprocess.run([vcgencmd, "<key>"])
            assert fake_vcgencmd.calls == [...]
    """
    calls: list[list[str]] = []
    responses: dict[str, CompletedProcess[str]] = {}

    def _setter(cmd_key: str, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        responses[cmd_key] = CompletedProcess(
            args=[cmd_key], returncode=returncode, stdout=stdout, stderr=stderr
        )

    def _fake_run(args: list[str], **kwargs: Any) -> CompletedProcess[str]:
        calls.append(list(args))
        key = args[1] if len(args) > 1 else ""
        if key in responses:
            return responses[key]
        return CompletedProcess(args=args, returncode=1, stdout="", stderr=f"unmocked: {args!r}")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    _setter.calls = calls  # type: ignore[attr-defined]
    return _setter
