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

// Bucket size for history aggregation — one entry per minute.
// Matches the /api/muon?agg=1m server-side aggregation and the
// `Math.floor(ts/60)*60` minute-floor formula used by buildMuonPlot's
// 90s safety margin (07-17).
const BUCKET_SEC = 60;

export function bufferMuonEvent(evt: MuonEvent): void {
  muonBuffer.push(evt);
  recentEventTimestamps.push(evt.ts);
}

export function flushMuonBuffer(): void {
  if (muonBuffer.length === 0) return;
  const drained = muonBuffer.splice(0);
  const nowSec = Math.floor(Date.now() / 1000);

  // Trim event timestamps to the rolling 60-second window (UNCHANGED from 07-10)
  recentEventTimestamps = recentEventTimestamps.filter(ts => ts > nowSec - 60);
  const liveRate = recentEventTimestamps.length;

  // Bucket new events by minute start
  const bucketIncrements = new Map<number, number>();
  for (const e of drained) {
    const bucketTs = Math.floor(e.ts / BUCKET_SEC) * BUCKET_SEC;
    bucketIncrements.set(bucketTs, (bucketIncrements.get(bucketTs) ?? 0) + 1);
  }

  muonStore.update(s => {
    // Merge increments into existing history (find-or-create per bucket)
    const byTs = new Map<number, MuonPoint>();
    for (const p of s.history) byTs.set(p.ts, { ts: p.ts, rate_per_min: p.rate_per_min });
    for (const [bucketTs, inc] of bucketIncrements) {
      const existing = byTs.get(bucketTs);
      byTs.set(bucketTs, {
        ts: bucketTs,
        rate_per_min: (existing?.rate_per_min ?? 0) + inc,
      });
    }
    // Sort ascending + trim to last 24h
    const merged = Array.from(byTs.values())
      .filter(p => p.ts > nowSec - 86400)
      .sort((a, b) => a.ts - b.ts);

    const last = drained[drained.length - 1];
    return {
      current: {
        ts: last.ts,
        rate_per_min: liveRate,
        detector_pressure_hpa: last.detector_pressure_hpa,
        detector_temp_c: last.detector_temp_c,
        latest_event_ts: last.ts,
      } as unknown as MuonData,
      history: merged,
      rate: liveRate,
      lastUpdateTs: nowSec,
    };
  });
}

export function setMuonSnapshot(data: MuonData | null): void {
  // Pre-warm the rolling-60s window from the server-computed rate so the
  // displayed muons/min doesn't dip on a fresh page load. Without this, the
  // live window (recentEventTimestamps) starts empty and under-counts for the
  // first 60s, making the number jump from the snapshot value down to a low
  // count and recover — visible as a "drop" on a freshly loaded device.
  // Only seed when the window is empty (first snapshot) so a later snapshot
  // (e.g. WS reconnect on an already-warm page) doesn't clobber real counts.
  if (
    data &&
    'rate_per_min' in data &&
    typeof data.rate_per_min === 'number' &&
    data.rate_per_min > 0 &&
    recentEventTimestamps.length === 0
  ) {
    const nowSec = Math.floor(Date.now() / 1000);
    const n = Math.round(data.rate_per_min);
    const seeded: number[] = [];
    for (let i = 0; i < n; i++) {
      // Spread synthetic timestamps across the last 60s; they expire naturally
      // as real events arrive over the next minute, converging to live counts.
      seeded.push(nowSec - 59 + Math.floor((i / n) * 60));
    }
    recentEventTimestamps = seeded;
  }
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
