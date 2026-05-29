"""snapshot-soak script — JSON output shape (QA-06).

Verifies the script writes a single dated JSON file with the locked schema,
even when /api/health is unreachable (the failure IS the evidence).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_snapshot_soak_writes_valid_json_when_health_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OBSERVATORY_SOAK_DIR", str(tmp_path))
    # Unreachable URL — script must still write the file with health=null + error key.
    monkeypatch.setenv("OBSERVATORY_HEALTH_URL", "http://127.0.0.1:1/blackhole")
    script = Path(__file__).resolve().parents[2] / "scripts" / "snapshot-soak.py"

    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env={**os.environ},
        check=False,
    )

    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1, f"expected exactly 1 snapshot file, got {files}"

    snap = json.loads(files[0].read_text())
    assert "captured_at" in snap
    assert snap["health"] is None
    assert "health_error" in snap
    assert snap["health_error"]  # non-empty error string
    assert isinstance(snap["journals"], dict)
    # All declared SERVICES present as keys, each maps to a list
    expected_services = {
        "obs-api",
        "obs-muon",
        "obs-usgs-poll",
        "obs-emsc-poll",
        "obs-bgs-poll",
        "obs-noaa-poll",
        "obs-aurora-poll",
        "obs-blitzortung",
        "mosquitto",
    }
    assert expected_services.issubset(snap["journals"].keys())
    for svc in expected_services:
        assert isinstance(snap["journals"][svc], list)
