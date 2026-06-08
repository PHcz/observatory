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
  return data.rows.map(r => ({ ts: r.ts, rate_per_min: (r.rate_per_min as number) ?? 0 }));
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
