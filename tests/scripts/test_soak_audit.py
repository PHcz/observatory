"""soak_audit script — 7-day summary shape (QA-06).

Asserts the end-of-soak audit walks a known 7-day fixture directory and emits
the documented summary fields on stdout.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_soak_audit_summarises_seven_day_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for day in range(1, 8):
        snap = {
            "captured_at": f"2026-06-{day:02d}T09:00:00Z",
            "health": {"status": "healthy", "pi": {"throttled": "0x0"}},
            "health_error": None,
            "journals": {},
        }
        (tmp_path / f"2026-06-{day:02d}.json").write_text(json.dumps(snap))

    monkeypatch.setenv("OBSERVATORY_SOAK_DIR", str(tmp_path))
    script = Path(__file__).resolve().parents[2] / "scripts" / "soak_audit.py"

    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env={**os.environ},
        check=False,
    )

    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    summary = json.loads(proc.stdout)
    assert summary["snapshots_found"] == 7
    assert summary["days_all_healthy"] == 7
    assert summary["pi_throttled_at_end"] == "0x0"
    assert len(summary["files"]) == 7


def test_soak_audit_handles_unhealthy_and_missing_pi_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 3 healthy, 4 unhealthy/null
    for day in range(1, 4):
        snap = {
            "captured_at": f"2026-06-{day:02d}T09:00:00Z",
            "health": {"status": "healthy", "pi": {"throttled": "0x0"}},
            "journals": {},
        }
        (tmp_path / f"2026-06-{day:02d}.json").write_text(json.dumps(snap))
    for day in range(4, 8):
        snap = {
            "captured_at": f"2026-06-{day:02d}T09:00:00Z",
            "health": None,
            "health_error": "ConnectError: nope",
            "journals": {},
        }
        (tmp_path / f"2026-06-{day:02d}.json").write_text(json.dumps(snap))

    monkeypatch.setenv("OBSERVATORY_SOAK_DIR", str(tmp_path))
    script = Path(__file__).resolve().parents[2] / "scripts" / "soak_audit.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env={**os.environ},
        check=False,
    )
    assert proc.returncode == 0
    summary = json.loads(proc.stdout)
    assert summary["snapshots_found"] == 7
    assert summary["days_all_healthy"] == 3
    # Last snapshot's health is None -> pi_throttled_at_end falls back to None
    assert summary["pi_throttled_at_end"] is None
