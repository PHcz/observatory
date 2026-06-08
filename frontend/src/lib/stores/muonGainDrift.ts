import { writable, type Writable } from 'svelte/store';
import type { MuonGainDriftResponse } from '$lib/types';
import { fetchMuonGainDrift } from '$lib/api/rest';

export interface MuonGainDriftState {
  data: MuonGainDriftResponse | null;
  lastFetchTs: number | null;
}

export const muonGainDriftStore: Writable<MuonGainDriftState> = writable({
  data: null,
  lastFetchTs: null,
});

/**
 * Replace the cached muon gain-drift snapshot. Used by the polling loop and by
 * panel tests (which drive MuonGainDriftPanel via setMuonGainDrift).
 */
export function setMuonGainDrift(data: MuonGainDriftResponse | null): void {
  muonGainDriftStore.set({ data, lastFetchTs: Math.floor(Date.now() / 1000) });
}

// Gain-drift tracking is weekly-granularity data; poll on mount + every 1 hour.
const MUON_GAIN_DRIFT_POLL_MS = 60 * 60 * 1000;
let muonGainDriftTimer: ReturnType<typeof setInterval> | null = null;

async function pollOnce(): Promise<void> {
  try {
    const data = await fetchMuonGainDrift();
    setMuonGainDrift(data);
  } catch {
    // Swallow — the panel shows its empty / stale state on fetch failure.
  }
}

export function initMuonGainDriftPolling(): () => void {
  void pollOnce();
  muonGainDriftTimer = setInterval(() => {
    void pollOnce();
  }, MUON_GAIN_DRIFT_POLL_MS);
  return () => {
    if (muonGainDriftTimer) {
      clearInterval(muonGainDriftTimer);
      muonGainDriftTimer = null;
    }
  };
}
