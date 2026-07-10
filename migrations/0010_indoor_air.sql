-- depends: 0009_muon_weekly_summary
-- Phase 14 INDOOR-02: indoor air node storage (CO2 + temp/humidity/pressure).
-- Fed by the ESP32-S2 + SCD-41 node over MQTT (indoor/<node>/sensor/<metric>/state),
-- coalesced into one row per ~60s reading by observatory.indoor.subscriber.
-- Multi-node from day one (node_id keyed). gas_index / lux / battery_v / wifi_rssi
-- are nullable — the current node is mains-powered and has no gas/light sensor,
-- so those stay NULL, but the schema is ready for richer nodes later.

CREATE TABLE indoor_air (
  id INTEGER PRIMARY KEY,
  node_id TEXT NOT NULL,           -- room label, e.g. 'living-room', 'bedroom'
  ts INTEGER NOT NULL,             -- Unix epoch (server receive time; node sends no ts)
  temp_c REAL,
  humidity_pct REAL,
  pressure_hpa REAL,
  co2_ppm INTEGER,
  gas_index REAL,                  -- nullable; BME688-class nodes only
  lux REAL,                        -- nullable; light-sensor nodes only
  battery_v REAL,                  -- NULL when mains-powered (the baseline node)
  wifi_rssi INTEGER,
  UNIQUE(node_id, ts)              -- dedup retained/replayed bursts within a second
);
CREATE INDEX idx_indoor_air_ts ON indoor_air(ts);
CREATE INDEX idx_indoor_air_node ON indoor_air(node_id);

CREATE TABLE indoor_events (
  id INTEGER PRIMARY KEY,
  node_id TEXT NOT NULL,
  ts INTEGER NOT NULL,
  event_type TEXT NOT NULL,        -- 'co2_high' | 'co2_resolved' | ...
  value REAL,
  detail TEXT
);
CREATE INDEX idx_indoor_events_ts ON indoor_events(ts);
CREATE INDEX idx_indoor_events_node ON indoor_events(node_id);
