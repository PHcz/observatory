import { writable, type Writable } from 'svelte/store';
import type { MuonAnalysisResponse } from '$lib/types';
import { fetchMuonAnalysis } from '$lib/api/rest';

export interface MuonAnalysisState {
  data: MuonAnalysisResponse | null;
  lastFetchTs: number | null;
}

export const muonAnalysisStore: Writable<MuonAnalysisState> = writable({
  data: null,
  lastFetchTs: null,
});

/**
 * Replace the cached muon-analysis snapshot. Used by the polling loop and by
 * the Wave-0 RED panel tests (which drive AdcSpectrumPanel/BarometricPanel via
 * setMuonAnalysis).
 */
export function setMuonAnalysis(data: MuonAnalysisResponse | null): void {
  muonAnalysisStore.set({ data, lastFetchTs: Math.floor(Date.now() / 1000) });
}

// The analysis recomputes from a rolling 7-day window; a 5-min UI poll keeps
// the histogram + barometric fit current without hammering the live endpoint.
const MUON_ANALYSIS_POLL_MS = 5 * 60 * 1000;
let muonAnalysisTimer: ReturnType<typeof setInterval> | null = null;

async function pollOnce(): Promise<void> {
  try {
    const data = await fetchMuonAnalysis();
    setMuonAnalysis(data);
  } catch {
    // Swallow — the panel shows its empty / stale state on fetch failure.
  }
}

export function initMuonAnalysisPolling(): () => void {
  void pollOnce();
  muonAnalysisTimer = setInterval(() => {
    void pollOnce();
  }, MUON_ANALYSIS_POLL_MS);
  return () => {
    if (muonAnalysisTimer) {
      clearInterval(muonAnalysisTimer);
      muonAnalysisTimer = null;
    }
  };
}
