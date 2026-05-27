-- depends: 0002_poller_runs
-- Phase 3: enforce UNIQUE(node_id, ts) on weather so replayed retained messages dedup via INSERT OR IGNORE.
CREATE UNIQUE INDEX idx_weather_node_id_ts ON weather(node_id, ts);
