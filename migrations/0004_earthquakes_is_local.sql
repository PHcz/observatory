-- depends: 0003_weather_unique
-- Phase 8.5 UI-18: flag local (UK or within OBSERVATORY_LOCAL_RADIUS_KM) earthquakes
-- so the dashboard EarthquakeList can highlight them. Backend pollers compute
-- is_local at insert time using HOME_LAT/HOME_LON + the configured radius.

ALTER TABLE earthquakes ADD COLUMN is_local INTEGER NOT NULL DEFAULT 0;

-- Backfill existing rows for BGS source (always UK; always local).
UPDATE earthquakes SET is_local = 1 WHERE source = 'bgs';
