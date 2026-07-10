import { writable, type Writable } from 'svelte/store';
import type { IndoorCurrentResponse } from '$lib/types';
import { fetchIndoorCurrent } from '$lib/api/rest';

export interface IndoorState {
  current: IndoorCurrentResponse | null;
  lastFetchTs: number | null;
}

export const indoorStore: Writable<IndoorState> = writable({
  current: null,
  lastFetchTs: null,
});

/** Replace the cached current-readings snapshot (used by the poller + tests). */
export function setIndoorCurrent(data: IndoorCurrentResponse | null): void {
  indoorStore.set({ current: data, lastFetchTs: Math.floor(Date.now() / 1000) });
}

// The node publishes every ~60 s; a 30 s UI poll keeps the hero value current.
const INDOOR_POLL_MS = 30 * 1000;
let indoorTimer: ReturnType<typeof setInterval> | null = null;

async function pollOnce(): Promise<void> {
  try {
    setIndoorCurrent(await fetchIndoorCurrent());
  } catch {
    // Swallow — the panel shows its empty / stale state on fetch failure.
  }
}

export function initIndoorPolling(): () => void {
  void pollOnce();
  indoorTimer = setInterval(() => void pollOnce(), INDOOR_POLL_MS);
  return () => {
    if (indoorTimer) {
      clearInterval(indoorTimer);
      indoorTimer = null;
    }
  };
}
