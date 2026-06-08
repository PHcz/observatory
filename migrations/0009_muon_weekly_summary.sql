-- depends: 0008_alerts
-- Phase 16 ENH-01: weekly MIP-peak ADC position summary for gain-drift tracking.
-- One row per ISO week (keyed on Monday 00:00 UTC epoch). The modal ADC bin center
-- from adc_histogram() is stored as the MIP-peak proxy — consistent with the
-- existing plot_histogram() approach in picomuon/histogram.py.
-- UNIQUE on week_start_ts prevents duplicate entries for the same week.

CREATE TABLE muon_weekly_summary (
  id INTEGER PRIMARY KEY,
  week_start_ts INTEGER NOT NULL UNIQUE,  -- Unix epoch of Monday 00:00 UTC for the week
  mip_peak_adc REAL NOT NULL,             -- modal ADC bin center (MIP-peak proxy)
  sample_events INTEGER NOT NULL,         -- coincidence event count used for histogram
  computed_ts INTEGER NOT NULL            -- Unix epoch when this row was computed
);
CREATE INDEX idx_muon_weekly_ts ON muon_weekly_summary(week_start_ts);
