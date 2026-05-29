// TypeScript interfaces mirroring the Phase 6 API contract

export interface WeatherData {
  ts: number;
  temp_c: number | null;
  humidity_pct: number | null;
  pressure_hpa: number | null;
  lux: number | null;
}

export interface MuonData {
  rate_per_min?: number; // ABSENT (not null) when no muon events yet
  latest_event_ts: number;
  detector_pressure_hpa: number | null;
  detector_temp_c: number | null;
}

export interface MuonEvent {
  ts: number;
  latest_event_ts: number;
  detector_pressure_hpa: number | null;
  detector_temp_c: number | null;
}

export interface SpaceWeatherData {
  ts: number;
  kp_index: number | null;
  solar_wind_kms: number | null;
  flare_class: string | null;
  flare_peak_ts: number | null;
}

export interface LightningSummary {
  past_hour: number;
  past_24h: number;
  nearest_km: number | null;
  total_today: number;
  hourly_buckets?: number[];  // length 24; [0]=oldest hour, [23]=most recent. Absent on partial WS frames (08-07).
  ts: number;
}

export interface AuroraData {
  ts: number;
  status: 'green' | 'yellow' | 'amber' | 'red';
  detail: string | null;
}

export interface EarthquakeItem {
  ts: number;
  source: 'usgs' | 'emsc' | 'bgs';
  magnitude: number | null;
  place: string | null;
  depth_km: number | null;
  // UI-18 (Phase 8.5 Plan 02): backend computes from HOME_LAT/HOME_LON +
  // OBSERVATORY_LOCAL_RADIUS_KM (default 250 km), or true for BGS source.
  // Optional for backward compat with pre-migration-0004 fixtures.
  is_local?: boolean;
}

export interface AstronomyData {
  sunrise_ts: number;
  sunset_ts: number;
  moon_phase: number;
  moon_illumination_pct: number;
}

export interface SnapshotData {
  timestamp: number;
  astronomy: AstronomyData | null;
  weather:   { freshness: 'healthy' | 'stale' | 'down'; data: WeatherData | null };
  muon:      { freshness: 'healthy' | 'stale' | 'down'; data: MuonData | null };
  space_weather: { freshness: 'healthy' | 'stale' | 'down'; data: SpaceWeatherData | null };
  lightning_summary: { freshness: 'healthy' | 'stale' | 'down'; data: LightningSummary }; // data always non-null
  aurora:    { freshness: 'healthy' | 'stale' | 'down'; data: AuroraData | null };
  earthquakes_recent: EarthquakeItem[];
}

export type WsEnvelope =
  | { type: 'snapshot'; data: SnapshotData; ts: number }
  | { type: 'weather';  data: WeatherData;  ts: number }
  | { type: 'muon';     data: MuonEvent;    ts: number }
  | { type: 'earthquake'; data: EarthquakeItem; ts: number }
  | { type: 'space_weather'; data: SpaceWeatherData; ts: number }
  | { type: 'lightning'; data: LightningSummary; ts: number }
  | { type: 'aurora';   data: AuroraData;   ts: number }
  | { type: 'ping';     ts: number }
  | { type: 'pong' };

export interface SourceHealth {
  last_event_ts: number | null;
  freshness: 'healthy' | 'stale' | 'down';
  staleness_threshold_sec: number;
  last_poll_status: string | null;
  last_poll_ts?: number;
  // UI-20 (Phase 8 Plan 05): backend marks sources whose silence has crossed
  // 2× expected interval. Drives CadenceWarningBanner + HealthRow amber tint.
  cadence_warning?: boolean;
}

export interface HealthResponse {
  timestamp: number;
  status: 'healthy' | 'stale' | 'down';
  local: {
    weather: SourceHealth;
    muon:    SourceHealth;
  };
  external: {
    usgs:        SourceHealth;
    emsc:        SourceHealth;
    bgs:         SourceHealth;
    noaa:        SourceHealth;
    blitzortung: SourceHealth;
    aurora:      SourceHealth;
  };
  pi: {
    temp_c: number | null;
    throttled: number | null;
    status: 'healthy' | 'warning' | 'critical';
    warnings: string[];
  };
}

// Chart series point types
export interface MuonPoint {
  ts: number;
  rate_per_min: number;
}

export interface WeatherPoint {
  ts: number;
  temp_c?: number | null;
  humidity_pct?: number | null;
  pressure_hpa?: number | null;
  lux?: number | null;
}

// Source keys and interval constants
export type SourceKey = 'weather' | 'muon' | 'usgs' | 'emsc' | 'bgs' | 'noaa' | 'blitzortung' | 'aurora';

export const INTERVALS_SEC: Record<SourceKey, number> = {
  weather:     300,
  muon:        5,
  usgs:        300,
  emsc:        300,
  bgs:         1800,
  noaa:        900,
  blitzortung: 30,
  aurora:      900,
};
