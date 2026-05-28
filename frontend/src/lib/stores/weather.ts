import { writable, type Writable } from 'svelte/store';
import type { WeatherData, WeatherPoint } from '$lib/types';

export interface WeatherState {
  current: WeatherData | null;
  history: WeatherPoint[];
  lastUpdateTs: number | null;
}

export const weatherStore: Writable<WeatherState> = writable({
  current: null,
  history: [],
  lastUpdateTs: null,
});

// 24-hour rolling window for the temperature chart (matches MuonChart pattern).
const HISTORY_WINDOW_SEC = 86_400;

export function setWeather(data: WeatherData): void {
  weatherStore.update(s => {
    // Append the new reading to history so the temperature chart redraws
    // live without a page refresh. Dedup by ts (a REST snapshot may already
    // include the current reading) and trim to the 24h window.
    const cutoff = Math.floor(Date.now() / 1000) - HISTORY_WINDOW_SEC;
    const existing = s.history.filter(p => p.ts > cutoff);
    const alreadyInHistory = existing.some(p => p.ts === data.ts);
    const nextHistory = alreadyInHistory
      ? existing
      : [...existing, { ts: data.ts, temp_c: data.temp_c }].sort((a, b) => a.ts - b.ts);
    return {
      ...s,
      current: data,
      history: nextHistory,
      lastUpdateTs: Math.floor(Date.now() / 1000),
    };
  });
}

export function seedWeatherHistory(points: WeatherPoint[]): void {
  weatherStore.update(s => ({ ...s, history: points }));
}
