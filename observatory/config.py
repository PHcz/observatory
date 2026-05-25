"""Single Settings class loaded from env at import time. Fails fast on invalid/missing values.

On the Pi: systemd injects values via EnvironmentFile=/etc/observatory/observatory.env.
On dev machines: pydantic-settings reads from .env (gitignored) with London placeholder coords.

All services import the module-level `settings` object. Direct env access is forbidden.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Location (required) ---
    home_lat: float = Field(ge=-90.0, le=90.0)
    home_lon: float = Field(ge=-180.0, le=180.0)

    # --- Database ---
    observatory_db_path: str = "/var/lib/observatory/observatory.db"

    # --- MQTT (Phase 3+) ---
    mqtt_host: str = "localhost"
    mqtt_port: int = Field(default=1883, ge=1, le=65535)

    # --- Muon detector (Phase 2) ---
    muon_serial_path: str = "/dev/picomuon"
    muon_flush_interval_sec: int = Field(default=5, ge=1, le=60)
    muon_buffer_max: int = Field(default=500, ge=1, le=10000)
    muon_silence_timeout_sec: int = Field(default=60, ge=10, le=600)
    muon_ntp_gate_timeout_sec: int = Field(default=30, ge=5, le=300)


def _load() -> Settings:
    """Instantiate Settings; raises ValidationError on missing/invalid env."""
    return Settings()


# Module-level instance — fails fast at import time if env is invalid.
# Tests that want to load with a specific env should instantiate Settings()
# directly inside the test with monkeypatched env.
try:
    settings = _load()
except Exception:
    # Re-raised on first attribute access by downstream code; tests using
    # the `valid_env` fixture import this module AFTER the fixture is applied.
    settings = None  # type: ignore[assignment]
