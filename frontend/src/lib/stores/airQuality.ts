import { writable, type Writable } from 'svelte/store';
import type { AirQualityResponse } from '$lib/types';
import { fetchAirQuality } from '$lib/api/rest';

export interface AirQualityState {
  data: AirQualityResponse | null;
  lastFetchTs: number | null;
}

export const airQualityStore: Writable<AirQualityState> = writable({
  data: null,
  lastFetchTs: null,
});

/**
 * Replace the cached air-quality snapshot. Used by the polling loop and by unit
 * tests (the Wave-0 RED AirQualityPanel test drives the panel via setAirQuality).
 */
export function setAirQuality(data: AirQualityResponse | null): void {
  airQualityStore.set({ data, lastFetchTs: Math.floor(Date.now() / 1000) });
}

// The poller refreshes hourly; a 15-min UI poll keeps the snapshot current
// without hammering the API (≤ the health/forecast polling cadence).
const AIR_QUALITY_POLL_MS = 15 * 60 * 1000;
let airQualityTimer: ReturnType<typeof setInterval> | null = null;

async function pollOnce(): Promise<void> {
  try {
    const data = await fetchAirQuality();
    setAirQuality(data);
  } catch {
    // Swallow — the panel shows its empty / stale state on fetch failure.
  }
}

export function initAirQualityPolling(): () => void {
  void pollOnce();
  airQualityTimer = setInterval(() => {
    void pollOnce();
  }, AIR_QUALITY_POLL_MS);
  return () => {
    if (airQualityTimer) {
      clearInterval(airQualityTimer);
      airQualityTimer = null;
    }
  };
}
