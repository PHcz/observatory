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

export function bufferMuonEvent(evt: MuonEvent): void {
  muonBuffer.push(evt);
}

export function flushMuonBuffer(): void {
  if (muonBuffer.length === 0) return;
  const drained = muonBuffer.splice(0);
  const nowSec = Math.floor(Date.now() / 1000);
  muonStore.update(s => {
    const newHistory = [
      ...s.history,
      ...drained.map(e => ({ ts: e.ts, rate_per_min: (e as unknown as { rate_per_min?: number }).rate_per_min ?? s.rate ?? 0 })),
    ].filter(p => p.ts > nowSec - 86400);
    const last = drained[drained.length - 1];
    const lastRate = (last as unknown as { rate_per_min?: number }).rate_per_min;
    return {
      current: {
        ts: last.ts,
        rate_per_min: lastRate,
        detector_pressure_hpa: last.detector_pressure_hpa,
        detector_temp_c: last.detector_temp_c,
        latest_event_ts: last.ts,
      } as unknown as MuonData,
      history: newHistory,
      rate: lastRate ?? s.rate,
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
