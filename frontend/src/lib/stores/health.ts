import { writable, type Writable } from 'svelte/store';
import type { HealthResponse } from '$lib/types';
import { fetchHealth } from '$lib/api/rest';

export interface HealthState {
  data: HealthResponse | null;
  lastFetchTs: number | null;
}

export const healthStore: Writable<HealthState> = writable({
  data: null,
  lastFetchTs: null,
});

const HEALTH_POLL_MS = 60000;
let healthTimer: ReturnType<typeof setInterval> | null = null;

async function pollOnce(): Promise<void> {
  try {
    const data = await fetchHealth();
    healthStore.set({ data, lastFetchTs: Math.floor(Date.now() / 1000) });
  } catch {
    // swallow — health row will show stale via WS status
  }
}

export function initHealthPolling(): () => void {
  void pollOnce();
  healthTimer = setInterval(() => { void pollOnce(); }, HEALTH_POLL_MS);
  return () => {
    if (healthTimer) {
      clearInterval(healthTimer);
      healthTimer = null;
    }
  };
}
