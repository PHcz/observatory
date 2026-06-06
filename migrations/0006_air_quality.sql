-- depends: 0005_forecast
-- Phase 11 OAQ-02: cached Open-Meteo air-quality snapshot (replace-on-fetch, one row).
-- Single current reading refreshed hourly by the air-quality poller. The poller
-- INSERT OR REPLACEs id=1 so growth is bounded at one row. air_quality_meta is the
-- /api/health freshness anchor (fetched_at), mirroring forecast_meta.

CREATE TABLE air_quality (
  id INTEGER PRIMARY KEY CHECK (id = 1),   -- single-row snapshot
  ts INTEGER NOT NULL,                      -- UTC epoch of the current reading (naive-local - utc_offset_seconds)
  european_aqi REAL,
  pm2_5 REAL,
  pm10 REAL,
  nitrogen_dioxide REAL,
  ozone REAL,
  sulphur_dioxide REAL,
  uv_index REAL,
  alder_pollen REAL,
  birch_pollen REAL,
  grass_pollen REAL,
  mugwort_pollen REAL,
  olive_pollen REAL,
  ragweed_pollen REAL,
  fetched_at INTEGER NOT NULL
);

CREATE TABLE air_quality_meta (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  fetched_at INTEGER NOT NULL,
  utc_offset_seconds INTEGER NOT NULL,
  timezone TEXT NOT NULL
);
