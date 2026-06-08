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

    # --- Phase 8.5 UI-18: local-quake highlight radius ---
    # Locked default 250 km per 08.5-CONTEXT (catches near-continental events
    # USGS/EMSC report alongside the UK BGS feed). Operator-tunable via env.
    observatory_local_radius_km: float = Field(
        default=250.0,
        ge=0.0,
        le=20000.0,
        description=(
            "UI-18 local-quake threshold: non-BGS events within this km radius "
            "of HOME_LAT/HOME_LON are flagged is_local"
        ),
    )

    # --- Database ---
    observatory_db_path: str = "/var/lib/observatory/observatory.db"

    # --- MQTT broker (Phase 3) ---
    mqtt_broker_host: str = Field(default="localhost", min_length=1)
    mqtt_broker_port: int = Field(default=1883, ge=1, le=65535)
    mqtt_username: str = Field(default="obs-api-subscriber")
    mqtt_password: str = Field(default="")  # gitignored secret; empty allowed for dev anon broker
    # --- Weather node (Phase 3) ---
    weather_nickname: str = Field(default="observatory-weather", min_length=1)
    weather_staleness_sec: int = Field(default=1800, ge=60, le=86400)
    weather_mqtt_topic_filter: str = Field(default="enviro/#")
    weather_subscriber_backoff_initial_sec: float = Field(default=1.0, ge=0.1, le=30.0)
    weather_subscriber_backoff_max_sec: float = Field(default=30.0, ge=1.0, le=600.0)

    # --- Weather node cadence-drift early warning (Phase 8 / UI-20) ---
    # Expected upload interval for the outdoor Enviro Weather node, in seconds.
    # Production default = 1500s (25 min, matches Pimoroni firmware default cadence).
    # Bench override: set WEATHER_EXPECTED_UPLOAD_SEC=300 during 5-min publish window
    # (Phase 3 plan 03-09 acceptance Part A). UI-20 banner triggers when the broker
    # hasn't received a publish for more than 2x this interval.
    weather_expected_upload_sec: int = Field(default=1500, ge=60, le=14400)

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

    # --- Open-Meteo local forecast (Phase 10, FCAST-01) ---
    # Keyless forecast feed. {lat}/{lon} are placeholders formatted at runtime in
    # observatory/pollers/forecast/__main__.py with settings.home_lat/home_lon —
    # coordinates are NEVER hard-coded in committed source (CLAUDE.md security gate).
    # timezone=auto resolves the IANA zone + returns utc_offset_seconds for local-day
    # math; defaults are metric (°C / km/h / % / mm) so no unit overrides are passed.
    # relative_humidity_2m + surface_pressure are requested to honour the locked
    # forecast-vs-actual temp+humidity+pressure decision (10-RESEARCH Open Q1).
    poller_forecast_url: str = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,apparent_temperature,relative_humidity_2m,surface_pressure,"
        "precipitation_probability,weather_code,wind_speed_10m"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
        "weather_code,wind_speed_10m_max"
        "&forecast_days=7&timezone=auto"
    )

    # --- Open-Meteo air quality (Phase 11, OAQ-01) ---
    # Keyless air-quality feed on a SEPARATE host (air-quality-api.open-meteo.com).
    # {lat}/{lon} are placeholders formatted at runtime in
    # observatory/pollers/airquality/__main__.py with settings.home_lat/home_lon —
    # coordinates are NEVER hard-coded in committed source (CLAUDE.md security gate).
    # timezone=auto resolves the IANA zone + returns utc_offset_seconds for the
    # naive-local→UTC carve-out. All 13 current= variables resolve under `current`
    # (Wave-0 fixture confirmed: european_aqi + 5 pollutants + uv_index + 6 pollen),
    # so no hourly fallback is needed. Pollen is CAMS-Europe only (sensible in EU).
    poller_air_quality_url: str = (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
        "?latitude={lat}&longitude={lon}"
        "&current=european_aqi,pm2_5,pm10,nitrogen_dioxide,ozone,sulphur_dioxide,uv_index,"
        "alder_pollen,birch_pollen,grass_pollen,mugwort_pollen,olive_pollen,ragweed_pollen"
        "&timezone=auto"
    )

    # --- NMDB / NEST neutron monitor (Phase 13, MU2-06) ---
    # Keyless NEST ASCII export of the Oulu neutron monitor (the canonical global
    # Forbush reference). {station} is substituted at runtime from
    # poller_nmdb_station so the station stays configurable. yunits=0 is MANDATORY
    # (Pitfall 3): it returns ABSOLUTE counts/s, not a relative/percent scale, which
    # the %-of-baseline math depends on. dtype=corr_for_efficiency + tresolution=60
    # gives ~hourly corrected counts; last_days=8 covers a full 7-day baseline window
    # with margin. Timestamps are UTC (parsed directly to epoch, not via the
    # naive-local carve-out). Host is www.nmdb.eu over HTTPS (NMDB-recommended modern
    # endpoint; rt.nmdb.eu is the legacy alias). NMDB asks scripted users to be gentle
    # and cite the database — hourly poll + observatory/0.1 UA is well within norms
    # (see observatory/pollers/nmdb/README.md).
    poller_nmdb_url: str = (
        "https://www.nmdb.eu/nest/draw_graph.php"
        "?formchk=1&stations[]={station}&tabchoice=revori&dtype=corr_for_efficiency"
        "&tresolution=60&yunits=0&date_choice=last&last_days=8&last_label=days_label"
        "&output=ascii"
    )
    poller_nmdb_station: str = "OULU"

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

    # --- Muon science (Phase 16, ENH-01/02) ---
    # Detector effective area for absolute flux in cm^-2 min^-1.
    # Default: 25.0 cm^2 (canonical PicoMuon value from picomuon/rates.py AREA_CM2).
    # Operator-tunable; set OBSERVATORY_EFFECTIVE_AREA_CM2 in Pi .env if area differs.
    effective_area_cm2: float = Field(default=25.0)
    # Cadence for the db_watcher MIP-peak gain-drift computation tick (seconds).
    muon_gain_drift_compute_interval_sec: int = Field(default=3600)

    # --- Station altitude for MSLP (Phase 16, ENH-05) ---
    # Set OBSERVATORY_STATION_ALTITUDE_M in Pi .env to the station altitude in metres.
    # Default 0.0 = sea level (no MSLP correction; station pressure ≈ MSLP).
    # Valid range: -500m (Dead Sea) to 9000m (Everest base camp).
    station_altitude_m: float = Field(default=0.0, ge=-500.0, le=9000.0)

    # --- Home timezone for local-midnight boundary (Phase 16, ENH-05) ---
    # IANA timezone string. Used for today-so-far midnight boundary calculation.
    # Set OBSERVATORY_HOME_TIMEZONE in Pi .env if not UK-based.
    home_timezone: str = Field(default="Europe/London")

    # --- Alert thresholds (Phase 16, ENH-04) — config-driven, never hardcoded ---
    # Frost/freeze rule: alert when temp_c below this AND dewpoint spread within spread limit.
    alert_frost_temp_c: float = Field(default=2.0)
    alert_frost_dewpoint_spread_c: float = Field(default=2.0)
    # Rapid pressure fall rule: alert when 3h pressure delta is more negative than this.
    alert_pressure_fall_hpa_per_3h: float = Field(default=1.6)
    # Hysteresis: minimum minutes a condition must be active before an ntfy push is sent.
    alert_min_active_minutes: int = Field(default=5)

    # --- ntfy integration (Phase 16, ENH-04) — the one sanctioned outbound exception ---
    # ntfy is a self-hostable push notification service. Default: disabled.
    # Set OBSERVATORY_ALERT_NTFY_ENABLED=true on the Pi .env to enable.
    alert_ntfy_enabled: bool = Field(default=False)
    alert_ntfy_url: str = Field(default="https://ntfy.sh")
    alert_ntfy_topic: str = Field(default="observatory-alerts")
    # Optional Bearer token for authenticated ntfy topics. Set on Pi only — never commit.
    alert_ntfy_token: str = Field(default="")

    # --- /ingest HTTP fallback basic auth (Phase 16, ENH-06) ---
    # HTTP basic-auth credentials for the POST /ingest fallback endpoint.
    # OBSERVATORY_INGEST_BASIC_AUTH_PASSWORD must be set on the Pi; empty blocks all ingest.
    ingest_basic_auth_user: str = Field(default="enviro")
    # Password lives only in Pi .env — never commit a real value.
    ingest_basic_auth_password: str = Field(default="")


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
