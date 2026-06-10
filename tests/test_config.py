"""INFRA-05: Settings loads from env, validates ranges, fails fast on missing/invalid values."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from observatory.config import Settings


def test_env_example_keys_map_to_settings_fields() -> None:
    """Every key in .env.example must be a real Settings field.

    Regression guard: Settings uses NO env_prefix, so an env var must equal a
    field name (case-insensitive). Phase-16 keys were wrongly templated with an
    `OBSERVATORY_` prefix (e.g. OBSERVATORY_STATION_ALTITUDE_M) which
    pydantic-settings silently ignores (extra="ignore") — so the documented keys
    had no effect. Only fields whose NAME starts with `observatory_` take that
    prefix in the env var.
    """
    env_example = Path(__file__).resolve().parent.parent / ".env.example"
    fields = set(Settings.model_fields)
    bad: list[str] = []
    for raw in env_example.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key.lower() not in fields:
            bad.append(key)
    assert not bad, (
        "These .env.example keys do not match any Settings field "
        f"(env has no prefix → env var == field name): {bad}"
    )


def test_loads_with_valid_env(valid_env: None) -> None:
    s = Settings()
    assert s.home_lat == pytest.approx(51.5074)
    assert s.home_lon == pytest.approx(-0.1278)
    assert s.mqtt_broker_host == "localhost"
    assert s.mqtt_broker_port == 1883


def test_missing_home_lat_raises(isolated_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_LON", "0.0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # disable .env fallback


def test_missing_home_lon_raises(isolated_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_LAT", "0.0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_home_lat_above_range_raises(isolated_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_LAT", "91.0")
    monkeypatch.setenv("HOME_LON", "0.0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_home_lat_below_range_raises(isolated_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_LAT", "-91.0")
    monkeypatch.setenv("HOME_LON", "0.0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_home_lon_above_range_raises(isolated_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_LAT", "0.0")
    monkeypatch.setenv("HOME_LON", "181.0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_mqtt_port_above_range_raises(isolated_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_LAT", "0.0")
    monkeypatch.setenv("HOME_LON", "0.0")
    monkeypatch.setenv("MQTT_BROKER_PORT", "70000")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_mqtt_port_zero_raises(isolated_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_LAT", "0.0")
    monkeypatch.setenv("HOME_LON", "0.0")
    monkeypatch.setenv("MQTT_BROKER_PORT", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_db_path_has_default(isolated_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME_LAT", "0.0")
    monkeypatch.setenv("HOME_LON", "0.0")
    s = Settings(_env_file=None)
    assert s.observatory_db_path == "/var/lib/observatory/observatory.db"


def test_case_insensitive(isolated_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """case_sensitive=False allows lowercase env var names too."""
    monkeypatch.setenv("home_lat", "12.0")
    monkeypatch.setenv("home_lon", "34.0")
    s = Settings(_env_file=None)
    assert s.home_lat == pytest.approx(12.0)
    assert s.home_lon == pytest.approx(34.0)


def test_no_direct_os_environ_in_observatory_package() -> None:
    """Discipline check: no service imports use os.environ.get for config."""
    import subprocess

    result = subprocess.run(
        ["grep", "-rn", "--include=*.py", "os.environ.get", "observatory"],
        capture_output=True,
        text=True,
        check=False,
    )
    # grep returns 1 when no matches found — that is the success case.
    assert result.returncode == 1, f"Found os.environ.get usage in observatory/:\n{result.stdout}"
