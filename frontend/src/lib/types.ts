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
  /** UTC epoch seconds of moonrise today, or null when the moon doesn't rise. */
  moonrise_ts?: number | null;
  /** UTC epoch seconds of moonset today, or null when the moon doesn't set. */
  moonset_ts?: number | null;
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

// Forecast (Phase 10 — /api/forecast). Shapes mirror the 10-03 router response.
export interface ForecastHourlyPoint {
  ts: number;
  temp_c: number | null;
  apparent_temp_c?: number | null;
  relative_humidity_pct?: number | null;
  surface_pressure_hpa?: number | null;
  precip_prob_pct: number | null;
  weather_code: number | null;
  wind_speed_kmh?: number | null;
}

export interface ForecastDailyPoint {
  ts: number;
  temp_max_c: number | null;
  temp_min_c: number | null;
  precip_prob_max_pct: number | null;
  weather_code: number | null;
  wind_speed_max_kmh?: number | null;
}

/** A single forecast-vs-actual temperature metric (10-03 _temp_metric). */
export interface ForecastTempMetric {
  forecast: number | null;
  actual: number | null;
  delta: number | null;
  label: 'cool' | 'warm' | 'on_track' | null;
  warn?: boolean;
}

/**
 * vs-actual block. The 10-03 router nests temp as `{high, low, actual}`; the
 * Wave-0 RED test feeds a flat `temp` ({forecast,actual,delta,label}). The
 * panel renders from whichever is present, so `temp` accepts both shapes.
 */
export interface ForecastVsActual {
  temp:
    | (ForecastTempMetric & { high?: never; low?: never })
    | { high: ForecastTempMetric; low: ForecastTempMetric; actual?: number | null };
  humidity?: { forecast: number | null; actual: number | null } | null;
  pressure?: { forecast: number | null; actual: number | null } | null;
  precip?: { prob_max: number | null } | null;
}

export interface ForecastResponse {
  hourly: ForecastHourlyPoint[];
  daily: ForecastDailyPoint[];
  vs_actual: ForecastVsActual | null;
  fetched_at: number | null;
}

// Air quality (Phase 11 — /api/air-quality). Single current snapshot.
export interface AirQualityPollutants {
  pm2_5: number | null;
  pm10: number | null;
  nitrogen_dioxide: number | null;
  ozone: number | null;
  sulphur_dioxide: number | null;
}
export interface AirQualityPollen {
  alder_pollen: number | null;
  birch_pollen: number | null;
  grass_pollen: number | null;
  mugwort_pollen: number | null;
  olive_pollen: number | null;
  ragweed_pollen: number | null;
}
export interface AirQualityResponse {
  aqi: number | null;
  pollutants: AirQualityPollutants;
  pollen: AirQualityPollen | null;
  uv: number | null;
  ts?: number;
  fetched_at: number | null;
}

// Phase 13 (MU2-05/06/07) — live muon science response types.

export interface AdcHistogramBin {
  bin_center: number;
  count: number;
}

export interface BarometricFitResult {
  beta: number;
  r_squared: number;
  p_value: number;
  n: number;
  // Per-bucket scatter points used in the fit (present when barometric is
  // non-null). Optional-safe for older payloads / RED test fixtures.
  points?: { pressure_hpa: number; rate_per_min: number }[];
}

export interface MuonAnalysisResponse {
  adc_histogram: AdcHistogramBin[];
  barometric: BarometricFitResult | null;
  raw_uncorrected: boolean;
}

export interface NmdbSeriesPoint {
  ts: number;
  counts_per_sec: number | null;
  pct_baseline: number | null;
}

export interface NmdbLocalPoint {
  ts: number;
  rate_per_min: number | null;
  pct_baseline: number | null;
}

export interface NmdbResponse {
  series: NmdbSeriesPoint[];
  local: NmdbLocalPoint[];
  baseline_window_days: number;
  fetched_at: number | null;
}

export type ForbushState = 'quiet' | 'watch' | 'forbush';

export interface ForbushResponse {
  state: ForbushState;
  nmdb_drop_pct: number | null;
  kp: number | null;
  solar_wind_kms: number | null;
  local_drop_pct: number | null;
  detail: string;
}

// Chart series point types
export interface MuonPoint {
  ts: number;
  rate_per_min: number;
  /** ±1σ Poisson confidence interval (ENH-02). Optional — absent on older cached rows. */
  lower_1sigma?: number | null;
  upper_1sigma?: number | null;
  /** Z-score of the bin relative to the rolling baseline (ENH-02). Null when uncalculated. */
  anomaly_z?: number | null;
  /** Severity flag when |z| threshold crossed. 'warn'=|z|>3, 'alert'=|z|>5. */
  anomaly_severity?: 'warn' | 'alert' | null;
  /** Pressure-corrected flux in cm⁻² min⁻¹ (ENH-01). Optional. */
  flux_cm2_min?: number | null;
}

// Phase 16 (ENH-01/02) — muon diagnostics + gain-drift response types.

export interface MuonDiagnosticsDtBin {
  bin_s: number;
  count: number;
}

export interface MuonDiagnosticsRatePmf {
  count_per_min: number;
  observed_prob: number;
  poisson_prob: number;
}

export interface MuonDiagnosticsResponse {
  dt_histogram: MuonDiagnosticsDtBin[];
  rate_pmf: MuonDiagnosticsRatePmf[];
  baseline_rate: number;
  sample_size_minutes: number;
}

export interface MuonGainDriftWeek {
  week_start_ts: number;
  mip_peak_adc: number;
  sample_events: number;
}

export interface MuonGainDriftResponse {
  weeks: MuonGainDriftWeek[];
  baseline_adc: number;
}

export interface WeatherPoint {
  ts: number;
  temp_c?: number | null;
  humidity_pct?: number | null;
  pressure_hpa?: number | null;
  lux?: number | null;
}

// Phase 16 (ENH-04/05) — weather intelligence types.

export interface AlertRow {
  id: number;
  rule: string;
  severity: 'warn' | 'alert';
  crossed_at_ts: number;
  resolved_at_ts: number | null;
  detail_text: string;
}

export interface AlertsResponse {
  active: AlertRow[];
  recent: AlertRow[];
}

export interface WeatherTodayResponse {
  high_c: number | null;
  low_c: number | null;
  pressure_high_hpa: number | null;
  pressure_low_hpa: number | null;
  peak_lux: number | null;
  dewpoint_high_c: number | null;
  dewpoint_low_c: number | null;
  since_ts: number | null;
}

export interface WeatherOutlookResponse {
  verdict: string | null;
  direction: string | null;
  based_on_hpa_per_3h: number | null;
  z_score: number | null;
  mslp_hpa: number | null;
  mslp_adjusted: boolean;
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
