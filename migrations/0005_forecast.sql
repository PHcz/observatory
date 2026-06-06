-- depends: 0004_earthquakes_is_local
-- Phase 10 FCAST-02: cached Open-Meteo forecast (replace-on-fetch cache).
-- Holds exactly one current forecast: ~168 hourly + 7 daily rows + 1 meta row,
-- refreshed hourly by the forecast poller. The poller DELETEs then bulk-INSERTs
-- so old (now-past) ts keys never linger; growth is bounded.

CREATE TABLE forecast_hourly (
  ts INTEGER PRIMARY KEY,            -- UTC epoch of the forecast hour (local time - utc_offset_seconds)
  temp_c REAL,
  apparent_temp_c REAL,
  relative_humidity_pct INTEGER,     -- added per 10-RESEARCH Open Question 1 (forecast-vs-actual humidity); not in the panel strip, sourced from hourly relative_humidity_2m
  surface_pressure_hpa REAL,         -- added per 10-RESEARCH Open Question 1 (forecast-vs-actual pressure); not in the panel strip, sourced from hourly surface_pressure
  precip_prob_pct INTEGER,           -- nullable; Open-Meteo can emit null
  weather_code INTEGER,              -- WMO code; frontend decodes to glyph/label
  wind_speed_kmh REAL,
  fetched_at INTEGER NOT NULL        -- when this forecast was retrieved
);
CREATE INDEX idx_forecast_hourly_ts ON forecast_hourly(ts);

CREATE TABLE forecast_daily (
  ts INTEGER PRIMARY KEY,            -- UTC epoch of the local-day start
  temp_max_c REAL,
  temp_min_c REAL,
  precip_prob_max_pct INTEGER,
  weather_code INTEGER,
  wind_speed_max_kmh REAL,
  fetched_at INTEGER NOT NULL
);
CREATE INDEX idx_forecast_daily_ts ON forecast_daily(ts);

CREATE TABLE forecast_meta (
  id INTEGER PRIMARY KEY CHECK (id = 1),  -- single-row table
  fetched_at INTEGER NOT NULL,            -- poll time → /api/health freshness anchor (Open Question 2: NOT MAX(ts), which is ~7d in the future)
  utc_offset_seconds INTEGER NOT NULL,
  timezone TEXT NOT NULL
);
