-- depends: 0007_nmdb
-- Phase 16 ENH-04: weather threshold alerts (frost + rapid-pressure-fall rules).
-- Active alerts have resolved_at_ts IS NULL; the partial index makes the
-- "is any alert active?" query O(active-count) not O(all-alerts).
-- crossed_at_ts records when the condition first triggered (transition edge);
-- resolved_at_ts is written when the condition clears (transition back).

CREATE TABLE alerts (
  id INTEGER PRIMARY KEY,
  rule TEXT NOT NULL,              -- 'frost_risk' | 'rapid_pressure_fall'
  severity TEXT NOT NULL,          -- 'warn' | 'alert'
  crossed_at_ts INTEGER NOT NULL,  -- Unix epoch when condition first triggered
  resolved_at_ts INTEGER,          -- NULL = still active; epoch when cleared
  detail_text TEXT NOT NULL        -- human-readable description for dashboard display
);
CREATE INDEX idx_alerts_active ON alerts(resolved_at_ts) WHERE resolved_at_ts IS NULL;
CREATE INDEX idx_alerts_ts ON alerts(crossed_at_ts);
