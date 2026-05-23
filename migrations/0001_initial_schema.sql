-- depends:
-- Initial schema for observatory: all 6 tables matching CLAUDE.md data model.
-- DO NOT MODIFY existing CREATE statements here once this migration has been
-- applied to any database. Create a NEW migration file for schema changes.

-- Local measurements
CREATE TABLE weather (
  id INTEGER PRIMARY KEY,
  node_id TEXT NOT NULL,
  ts INTEGER NOT NULL,
  temp_c REAL,
  humidity_pct REAL,
  pressure_hpa REAL,
  lux REAL,                     -- from LTR-559 light sensor
  battery_v REAL,
  wifi_rssi INTEGER
);
CREATE INDEX idx_weather_ts ON weather(ts);

CREATE TABLE muon_events (
  id INTEGER PRIMARY KEY,
  ts INTEGER NOT NULL,
  detector_pressure_hpa REAL,
  detector_temp_c REAL,
  amplitude REAL,
  coincidence INTEGER
);
CREATE INDEX idx_muon_ts ON muon_events(ts);

-- External data
CREATE TABLE earthquakes (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,         -- 'usgs' | 'emsc' | 'bgs'
  external_id TEXT NOT NULL,    -- source's event ID, for dedup
  ts INTEGER NOT NULL,
  magnitude REAL,
  depth_km REAL,
  latitude REAL,
  longitude REAL,
  place TEXT,
  UNIQUE(source, external_id)
);
CREATE INDEX idx_quakes_ts ON earthquakes(ts);
CREATE INDEX idx_quakes_mag ON earthquakes(magnitude);

CREATE TABLE space_weather (
  id INTEGER PRIMARY KEY,
  ts INTEGER NOT NULL,
  kp_index REAL,
  solar_wind_kms REAL,
  flare_class TEXT,             -- 'X1.2', 'M3.4', 'C2.1', etc
  flare_peak_ts INTEGER         -- nullable
);
CREATE INDEX idx_sw_ts ON space_weather(ts);

CREATE TABLE lightning_strikes (
  id INTEGER PRIMARY KEY,
  ts INTEGER NOT NULL,
  latitude REAL,
  longitude REAL,
  distance_km REAL              -- pre-computed from home location
);
CREATE INDEX idx_lightning_ts ON lightning_strikes(ts);

CREATE TABLE aurora_status (
  id INTEGER PRIMARY KEY,
  ts INTEGER NOT NULL,
  status TEXT NOT NULL,         -- 'green' | 'yellow' | 'amber' | 'red'
  detail TEXT
);
CREATE INDEX idx_aurora_ts ON aurora_status(ts);
