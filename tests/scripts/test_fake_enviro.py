"""CLI surface test for scripts/fake-enviro.py — no broker required."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "fake-enviro.py"


def test_help_runs() -> None:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert r.returncode == 0
    assert "--broker-host" in r.stdout
    assert "--burst-size" in r.stdout
    assert "--nickname" in r.stdout
    assert "--interval" in r.stdout


def _load_module():
    spec = importlib.util.spec_from_file_location("fake_enviro", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_payload_shape() -> None:
    mod = _load_module()
    p = mod._build_payload("observatory-weather")
    assert p["nickname"] == "observatory-weather"
    assert p["model"] == "weather"
    assert set(p["readings"].keys()) >= {
        "temperature",
        "humidity",
        "pressure",
        "light",
        "voltage",
    }
    assert "Z" in p["timestamp"]


def test_build_payload_parses_via_weather_envelope() -> None:
    """Fake publisher output must satisfy the production parser."""
    mod = _load_module()
    from observatory.weather.payload import WeatherEnvelope

    payload = mod._build_payload("observatory-weather", uid="devstub-0007")
    env = WeatherEnvelope.model_validate_json(json.dumps(payload))
    assert env.nickname == "observatory-weather"
    assert env.model == "weather"
    assert env.uid == "devstub-0007"


def test_build_payload_uid_override() -> None:
    mod = _load_module()
    p = mod._build_payload("rogue-device", uid="devstub-0042")
    assert p["nickname"] == "rogue-device"
    assert p["uid"] == "devstub-0042"


def test_reading_value_ranges() -> None:
    """Synthetic readings should be in plausible Pimoroni ranges."""
    mod = _load_module()
    for _ in range(20):
        p = mod._build_payload("observatory-weather")
        r = p["readings"]
        assert 8.0 <= r["temperature"] <= 22.0
        assert 40.0 <= r["humidity"] <= 85.0
        assert 990.0 <= r["pressure"] <= 1025.0
        assert 0.0 <= r["light"] <= 800.0
        assert 2.4 <= r["voltage"] <= 2.8
