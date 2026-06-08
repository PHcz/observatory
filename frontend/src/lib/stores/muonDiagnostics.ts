import { writable, type Writable } from 'svelte/store';
import type { MuonDiagnosticsResponse } from '$lib/types';
import { fetchMuonDiagnostics } from '$lib/api/rest';

export interface MuonDiagnosticsState {
  data: MuonDiagnosticsResponse | null;
  lastFetchTs: number | null;
}

export const muonDiagnosticsStore: Writable<MuonDiagnosticsState> = writable({
  data: null,
  lastFetchTs: null,
});

/**
 * Replace the cached muon-diagnostics snapshot. Used by the polling loop and by
 * panel tests (which drive MuonDiagnosticsPanel via setMuonDiagnostics).
 */
export function setMuonDiagnostics(data: MuonDiagnosticsResponse | null): void {
  muonDiagnosticsStore.set({ data, lastFetchTs: Math.floor(Date.now() / 1000) });
}

// Diagnostics compute from recent event stream; a 5-min UI poll keeps the
// histogram + PMF current without hammering the endpoint.
const MUON_DIAGNOSTICS_POLL_MS = 5 * 60 * 1000;
let muonDiagnosticsTimer: ReturnType<typeof setInterval> | null = null;

async function pollOnce(): Promise<void> {
  try {
    const data = await fetchMuonDiagnostics();
    setMuonDiagnostics(data);
  } catch {
    // Swallow — the panel shows its empty / stale state on fetch failure.
  }
}

export function initMuonDiagnosticsPolling(): () => void {
  void pollOnce();
  muonDiagnosticsTimer = setInterval(() => {
    void pollOnce();
  }, MUON_DIAGNOSTICS_POLL_MS);
  return () => {
    if (muonDiagnosticsTimer) {
      clearInterval(muonDiagnosticsTimer);
      muonDiagnosticsTimer = null;
    }
  };
}
