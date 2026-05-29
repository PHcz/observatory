import { derived, writable, type Readable, type Writable } from 'svelte/store';
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
      : [
          ...existing,
          {
            ts: data.ts,
            temp_c: data.temp_c,
            humidity_pct: data.humidity_pct ?? null,
            pressure_hpa: data.pressure_hpa ?? null,
            lux: data.lux ?? null,
          },
        ].sort((a, b) => a.ts - b.ts);
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

/**
 * Maximum lux observed since local midnight. Updates reactively as
 * weatherStore.history grows. Returns null when no non-null lux readings
 * exist for today (e.g. fresh page load at 00:01, sensor failure).
 *
 * Local midnight = today's start in the browser's local timezone, so the
 * "today" definition tracks the user's wall clock and rolls over automatically.
 */
export const maxLuxToday: Readable<number | null> = derived(weatherStore, ($s) => {
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  const cutoffSec = Math.floor(todayStart.getTime() / 1000);
  const luxValues = $s.history
    .filter(p => p.ts >= cutoffSec && p.lux != null)
    .map(p => p.lux as number);
  if (luxValues.length === 0) return null;
  return Math.max(...luxValues);
});
