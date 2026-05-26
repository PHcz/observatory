import type { MuonPoint, WeatherPoint, HealthResponse } from '$lib/types';

export function fetchMuonHistory(_from: number, _to: number): Promise<MuonPoint[]> { throw new Error('NOT_IMPLEMENTED'); }
export function fetchWeatherHistory(_from: number, _to: number): Promise<WeatherPoint[]> { throw new Error('NOT_IMPLEMENTED'); }
export function fetchHealth(): Promise<HealthResponse> { throw new Error('NOT_IMPLEMENTED'); }
