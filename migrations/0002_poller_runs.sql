-- depends: 0001_initial_schema
-- Adds the poller_runs audit-trail table for Phase 4 earthquake pollers.
-- Every poller invocation writes one row at exit (success or failure).
-- Phase 5's /api/health endpoint will read MAX(ended_at) per source.

CREATE TABLE poller_runs (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,         -- 'usgs' | 'emsc' | 'bgs' | future poller names
  started_at INTEGER NOT NULL,  -- unix epoch seconds
  ended_at INTEGER NOT NULL,
  status TEXT NOT NULL,         -- 'success' | 'transient_fail' | 'parse_fail' | 'db_fail' | 'network_unreachable'
  events_fetched INTEGER NOT NULL DEFAULT 0,
  events_written INTEGER NOT NULL DEFAULT 0,
  error_summary TEXT            -- nullable; first 200 chars of last error if status != 'success'
);
CREATE INDEX idx_poller_runs_source_ended ON poller_runs(source, ended_at);
