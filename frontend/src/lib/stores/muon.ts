import { writable, type Writable } from 'svelte/store';
import type { MuonData, MuonPoint, MuonEvent } from '$lib/types';

export interface MuonState {
  current: MuonData | null;
  history: MuonPoint[];
  rate: number | null;
  lastUpdateTs: number | null;
}

export const muonStore: Writable<MuonState> = writable({
  current: null,
  history: [],
  rate: null,
  lastUpdateTs: null,
});

let muonBuffer: MuonEvent[] = [];
let recentEventTimestamps: number[] = [];

export function bufferMuonEvent(evt: MuonEvent): void {
  muonBuffer.push(evt);
  recentEventTimestamps.push(evt.ts);
}

export function flushMuonBuffer(): void {
  if (muonBuffer.length === 0) return;
  const drained = muonBuffer.splice(0);
  const nowSec = Math.floor(Date.now() / 1000);
  // Trim event timestamps to the rolling 60-second window
  recentEventTimestamps = recentEventTimestamps.filter(ts => ts > nowSec - 60);
  const liveRate = recentEventTimestamps.length;
  muonStore.update(s => {
    const newHistory = [
      ...s.history,
      ...drained.map(e => ({ ts: e.ts, rate_per_min: liveRate })),
    ].filter(p => p.ts > nowSec - 86400);
    const last = drained[drained.length - 1];
    return {
      current: {
        ts: last.ts,
        rate_per_min: liveRate,
        detector_pressure_hpa: last.detector_pressure_hpa,
        detector_temp_c: last.detector_temp_c,
        latest_event_ts: last.ts,
      } as unknown as MuonData,
      history: newHistory,
      rate: liveRate,
      lastUpdateTs: nowSec,
    };
  });
}

export function setMuonSnapshot(data: MuonData | null): void {
  muonStore.update(s => ({
    ...s,
    current: data,
    rate: data && 'rate_per_min' in data ? (data.rate_per_min ?? null) : null,
    lastUpdateTs: Math.floor(Date.now() / 1000),
  }));
}

export function seedMuonHistory(points: MuonPoint[]): void {
  muonStore.update(s => ({ ...s, history: points }));
}

// Test-only: reset the rolling-60s event window. Production code never calls this.
export function _resetMuonRateWindow(): void {
  recentEventTimestamps = [];
  muonBuffer = [];
}
