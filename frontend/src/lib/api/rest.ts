import type {
  MuonPoint,
  WeatherPoint,
  HealthResponse,
  ForecastResponse,
  AirQualityResponse,
  MuonAnalysisResponse,
  NmdbResponse,
  ForbushResponse,
  MuonDiagnosticsResponse,
  MuonGainDriftResponse,
  AlertsResponse,
  WeatherTodayResponse,
  WeatherOutlookResponse,
  IndoorCurrentResponse,
  IndoorHistoryResponse,
} from '$lib/types';

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
  if (!res.ok) throw new Error(`HTTP ${res.status} ${url}`);
  return res.json() as Promise<T>;
}

interface TimeSeriesRow { ts: number; [k: string]: number | null; }
interface TimeSeriesResponse {
  window: { from: number; to: number };
  bucket_size_sec: number;
  agg: string;
  rows: TimeSeriesRow[];
}

export async function fetchMuonHistory(from: number, to: number): Promise<MuonPoint[]> {
  const data = await getJson<TimeSeriesResponse>(`/api/muon?from=${from}&to=${to}&agg=auto`);
  // Carry ALL Phase-16 fields — the rate chart's sea-level flux annotation
  // (flux_cm2_min, ENH-01), Poisson confidence band (lower/upper_1sigma, ENH-02),
  // and anomaly markers (anomaly_z/anomaly_severity, ENH-02) each read a different
  // one. Mapping only rate_per_min leaves all three permanently inert (same class
  // of bug as the weather history fetch below).
  return data.rows.map(r => ({
    ts: r.ts,
    rate_per_min: (r.rate_per_min as number) ?? 0,
    flux_cm2_min: (r.flux_cm2_min as number | null) ?? null,
    lower_1sigma: (r.lower_1sigma as number | null) ?? null,
    upper_1sigma: (r.upper_1sigma as number | null) ?? null,
    anomaly_z: (r.anomaly_z as number | null) ?? null,
    anomaly_severity: (r.anomaly_severity as 'warn' | 'alert' | null) ?? null,
  }));
}

export async function fetchWeatherHistory(from: number, to: number): Promise<WeatherPoint[]> {
  const data = await getJson<TimeSeriesResponse>(`/api/weather?from=${from}&to=${to}&agg=auto`);
  // Carry ALL sensor fields — the temperature, pressure, humidity, and light
  // charts each read a different one. Mapping only temp_c (the original Phase 7
  // code) leaves the UI-19 pressure/humidity/light charts permanently empty.
  return data.rows.map(r => ({
    ts: r.ts,
    temp_c: (r.temp_c as number | null) ?? null,
    humidity_pct: (r.humidity_pct as number | null) ?? null,
    pressure_hpa: (r.pressure_hpa as number | null) ?? null,
    lux: (r.lux as number | null) ?? null,
  }));
}

export async function fetchHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>('/api/health');
}

export async function fetchForecast(): Promise<ForecastResponse> {
  return getJson<ForecastResponse>('/api/forecast');
}

export async function fetchAirQuality(): Promise<AirQualityResponse> {
  return getJson<AirQualityResponse>('/api/air-quality');
}

// Phase 13 (MU2-05/06/07) — live muon science feeds.

export async function fetchMuonAnalysis(): Promise<MuonAnalysisResponse> {
  return getJson<MuonAnalysisResponse>('/api/muon/analysis');
}

export async function fetchNmdb(): Promise<NmdbResponse> {
  return getJson<NmdbResponse>('/api/nmdb');
}

export async function fetchForbush(): Promise<ForbushResponse> {
  return getJson<ForbushResponse>('/api/forbush');
}

// Phase 16 (ENH-01/02) — muon diagnostics + gain-drift feeds.

export async function fetchMuonDiagnostics(): Promise<MuonDiagnosticsResponse> {
  return getJson<MuonDiagnosticsResponse>('/api/muon/diagnostics');
}

export async function fetchMuonGainDrift(): Promise<MuonGainDriftResponse> {
  return getJson<MuonGainDriftResponse>('/api/muon/gain-drift');
}

// Phase 16 (ENH-04/05) — weather intelligence feeds.

export async function fetchAlerts(): Promise<AlertsResponse> {
  return getJson<AlertsResponse>('/api/alerts');
}

export async function fetchWeatherToday(): Promise<WeatherTodayResponse> {
  return getJson<WeatherTodayResponse>('/api/weather/today');
}

export async function fetchWeatherOutlook(): Promise<WeatherOutlookResponse> {
  return getJson<WeatherOutlookResponse>('/api/weather/outlook');
}

// Phase 15 — indoor air node(s).

export async function fetchIndoorCurrent(): Promise<IndoorCurrentResponse> {
  return getJson<IndoorCurrentResponse>('/api/indoor/current');
}

export async function fetchIndoorHistory(hours = 24, node?: string): Promise<IndoorHistoryResponse> {
  const q = node ? `?hours=${hours}&node=${encodeURIComponent(node)}` : `?hours=${hours}`;
  return getJson<IndoorHistoryResponse>(`/api/indoor/history${q}`);
}
