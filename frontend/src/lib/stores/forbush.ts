import { writable, type Writable } from 'svelte/store';
import type { ForbushResponse } from '$lib/types';
import { fetchForbush } from '$lib/api/rest';

export interface ForbushState {
  data: ForbushResponse | null;
  lastFetchTs: number | null;
}

export const forbushStore: Writable<ForbushState> = writable({
  data: null,
  lastFetchTs: null,
});

/**
 * Replace the cached Forbush snapshot. Used by the polling loop and by the
 * Wave-0 RED ForbushPanel test (which drives the chip via setForbush).
 */
export function setForbush(data: ForbushResponse | null): void {
  forbushStore.set({ data, lastFetchTs: Math.floor(Date.now() / 1000) });
}

// The Forbush indicator derives from the hourly NMDB feed + NOAA Kp; a 5-min
// UI poll keeps the chip current without hammering the local endpoint.
const FORBUSH_POLL_MS = 5 * 60 * 1000;
let forbushTimer: ReturnType<typeof setInterval> | null = null;

async function pollOnce(): Promise<void> {
  try {
    const data = await fetchForbush();
    setForbush(data);
  } catch {
    // Swallow — the chip shows Quiet / awaiting-data state on fetch failure.
  }
}

export function initForbushPolling(): () => void {
  void pollOnce();
  forbushTimer = setInterval(() => {
    void pollOnce();
  }, FORBUSH_POLL_MS);
  return () => {
    if (forbushTimer) {
      clearInterval(forbushTimer);
      forbushTimer = null;
    }
  };
}
