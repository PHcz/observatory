import { writable, type Writable } from 'svelte/store';
import type { ForecastResponse } from '$lib/types';
import { fetchForecast } from '$lib/api/rest';

export interface ForecastState {
  data: ForecastResponse | null;
  lastFetchTs: number | null;
}

export const forecastStore: Writable<ForecastState> = writable({
  data: null,
  lastFetchTs: null,
});

/**
 * Replace the cached forecast. Used by the polling loop and by unit tests
 * (the Wave-0 RED ForecastPanel test drives the panel via setForecast).
 */
export function setForecast(data: ForecastResponse): void {
  forecastStore.set({ data, lastFetchTs: Math.floor(Date.now() / 1000) });
}

// The poller refreshes hourly; a 15-min UI poll keeps the next-24h slice
// current without hammering the API (≤ the health/muon polling cadence).
const FORECAST_POLL_MS = 15 * 60 * 1000;
let forecastTimer: ReturnType<typeof setInterval> | null = null;

async function pollOnce(): Promise<void> {
  try {
    const data = await fetchForecast();
    setForecast(data);
  } catch {
    // Swallow — the panel shows its empty / stale state on fetch failure.
  }
}

export function initForecastPolling(): () => void {
  void pollOnce();
  forecastTimer = setInterval(() => {
    void pollOnce();
  }, FORECAST_POLL_MS);
  return () => {
    if (forecastTimer) {
      clearInterval(forecastTimer);
      forecastTimer = null;
    }
  };
}
