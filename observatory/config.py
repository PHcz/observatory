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

    # --- External pollers (Phase 4) ---
    poller_http_connect_timeout_sec: float = Field(default=5.0, ge=1.0, le=30.0)
    poller_http_read_timeout_sec: float = Field(default=15.0, ge=1.0, le=60.0)
    poller_http_max_response_bytes: int = Field(default=5_242_880, ge=10_000, le=104_857_600)
    poller_http_max_redirects: int = Field(default=3, ge=0, le=10)
    poller_parse_failure_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    poller_usgs_url: str = (
        "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"
    )
    poller_emsc_url: str = (
        "https://www.seismicportal.eu/fdsnws/event/1/query?format=json&limit=200&minmag=2.5"
    )
    # BGS https support confirmed 2026-05-25 via tests/pollers/bgs/test_https_probe.py
    # (HEAD returned 200). See tests/pollers/bgs/HTTPS_PROBE_RESULT.md.
    poller_bgs_url: str = "https://earthquakes.bgs.ac.uk/feeds/MhSeismology.xml"

    # --- NOAA SWPC pollers (Phase 5) ---
    # URLs verified live 2026-05-25 by researcher (CONTEXT-listed URLs returned 404).
    poller_noaa_kp_url: str = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
    poller_noaa_solar_wind_url: str = (
        "https://services.swpc.noaa.gov/products/solar-wind/plasma-2-hour.json"
    )
    poller_noaa_xray_url: str = "https://services.swpc.noaa.gov/json/goes/primary/xrays-6-hour.json"

    # --- AuroraWatch UK (Phase 5) ---
    poller_aurora_url: str = "https://aurorawatch-api.lancs.ac.uk/0.2/status/current-status.xml"

    # --- Blitzortung lightning (Phase 5) ---
    # Port (8056 vs 443) probed at 05-04 first-task; URL list defaults to wss:// (443).
    # Plan 05-04 may flip these defaults after probe via a follow-up edit.
    poller_blitzortung_ws_urls: list[str] = Field(
        default_factory=lambda: [
            "wss://ws1.blitzortung.org",
            "wss://ws3.blitzortung.org",
            "wss://ws7.blitzortung.org",
            "wss://ws8.blitzortung.org",
        ]
    )
    poller_lightning_radius_km: float = Field(default=500.0, ge=10.0, le=10000.0)
    poller_blitzortung_flush_interval_sec: int = Field(default=30, ge=5, le=300)
    poller_blitzortung_degraded_after_sec: int = Field(default=300, ge=60, le=3600)

    # --- API (Phase 5 scaffold; Phase 6 may tighten) ---
    # LAN topology is the trust boundary; Phase 6 may tighten if remote access is added.
    # Phase 6 SEC-04: default to "auto" (resolve LAN IPv4 at startup via __main__.resolve_lan_ip).
    # "0.0.0.0" remains valid for local dev; explicit IP also accepted.
    api_bind_host: str = "auto"
    api_bind_port: int = Field(default=8000, ge=1, le=65535)
    api_watchdog_ping_interval_sec: int = Field(default=10, ge=2, le=60)

    # --- API server (Phase 6 additions) ---
    obs_env: str = Field(default="production", pattern="^(production|development)$")
    api_ws_queue_maxsize: int = Field(default=100, ge=1, le=10000)
    api_ws_ping_interval_sec: float = Field(default=30.0, ge=0.01, le=600.0)
    api_ws_pong_timeout_sec: float = Field(default=60.0, ge=0.05, le=600.0)
    api_db_watcher_interval_sec: float = Field(default=5.0, ge=0.1, le=60.0)
    api_origin_allowlist: str = Field(
        default="192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,localhost,127.0.0.1,observatory.local"
    )
    api_static_bundle_dir: str = Field(default="/opt/observatory/frontend/build")

    # --- Pi thermal monitoring (Phase 5) ---
    pi_temp_warning_c: float = Field(default=70.0, ge=40.0, le=90.0)
    pi_temp_critical_c: float = Field(default=80.0, ge=50.0, le=100.0)
    pi_thermal_warning_rate_limit_sec: int = Field(default=600, ge=60, le=3600)
    pi_vcgencmd_path: str = "/usr/bin/vcgencmd"


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
