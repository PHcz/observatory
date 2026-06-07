-- depends: 0006_air_quality
-- Phase 13 MU2-06: cached NMDB neutron-monitor counts (Oulu default) + freshness anchor.
-- Append window (INSERT OR IGNORE on UNIQUE(station, ts)); nmdb_meta is the
-- /api/health freshness anchor (fetched_at), mirroring forecast_meta/air_quality_meta.
-- NMDB timestamps are UTC (parsed directly to epoch), NOT via the naive-local
-- carve-out used by forecast/air_quality — so nmdb_meta carries no utc_offset_seconds.

CREATE TABLE nmdb_counts (
  id INTEGER PRIMARY KEY,
  station TEXT NOT NULL,            -- 'OULU' (configurable, default OULU)
  ts INTEGER NOT NULL,             -- UTC epoch, BEGIN of the NMDB measurement interval
  counts_per_sec REAL,             -- yunits=0 counts/s; nullable for gaps
  UNIQUE(station, ts)
);
CREATE INDEX idx_nmdb_ts ON nmdb_counts(ts);

CREATE TABLE nmdb_meta (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  fetched_at INTEGER NOT NULL,
  station TEXT NOT NULL
);
