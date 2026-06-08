import { writable, derived, type Writable, type Readable } from 'svelte/store';
import type { MuonData, MuonPoint, MuonEvent } from '$lib/types';
import { stpCorrectedRate } from '$lib/utils/stp';

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
    // Preserve the full REST-seeded row (flux_cm2_min, Poisson band, anomaly
    // fields — ENH-01/02), not just ts+rate. Spreading keeps those fields alive
    // across live WS flushes; otherwise the rate chart's annotation/band/dots go
    // permanently inert after the first flush. Live-edge buckets get fresh
    // server-computed fields on the next 5-min REST reseed (and are excluded from
    // rendering by the 90s safety margin anyway).
    for (const p of s.history) byTs.set(p.ts, { ...p });
    for (const [bucketTs, inc] of bucketIncrements) {
      const existing = byTs.get(bucketTs);
      byTs.set(bucketTs, {
        ...existing,
        ts: bucketTs,
        rate_per_min: (existing?.rate_per_min ?? 0) + inc,
      });
    }
    // Sort ascending + trim to last 24h
    const merged = Array.from(byTs.values())
      .filter(p => p.ts > nowSec - 86400)
      .sort((a, b) => a.ts - b.ts);

    const last = drained[drained.length - 1];
    // Pressure-correct the displayed live rate (StatsRow shows it as "pressure
    // corrected") using the latest event's detector temp + pressure. Falls back
    // to the raw count when T/P is missing. (UKRAA STP method — see utils/stp.)
    const correctedRate =
      stpCorrectedRate(liveRate, last.detector_temp_c, last.detector_pressure_hpa) ?? liveRate;
    return {
      current: {
        ts: last.ts,
        rate_per_min: correctedRate,
        detector_pressure_hpa: last.detector_pressure_hpa,
        detector_temp_c: last.detector_temp_c,
        latest_event_ts: last.ts,
      } as unknown as MuonData,
      history: merged,
      rate: correctedRate,
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

/**
 * Mean rate over the last `minutes` COMPLETE minute buckets in history.
 *
 * The StatsRow muon number previously used the client-side rolling-60s WS event
 * count (`muonStore.rate`), which systematically UNDER-counts: it only sees
 * events the browser actually received in the trailing 60s, so WS latency/loss
 * and any browser/event clock-window skew drop events the detector really
 * recorded. The per-minute `history` is reconciled with the server every 5 min
 * (+ on tab-refocus) and is STP pressure-corrected, so it's authoritative.
 *
 * Excludes the in-progress current minute (still filling → partial count) and
 * averages a few complete minutes to match the chart's smoothed endpoint and
 * damp Poisson jitter (no more per-second flicker). Returns null if there is no
 * complete bucket yet.
 */
export function recentMeanRate(
  history: MuonPoint[],
  nowSec: number,
  minutes = 5,
): number | null {
  const currentMinuteStart = Math.floor(nowSec / 60) * 60;
  const complete = history.filter((p) => p.ts < currentMinuteStart);
  if (complete.length === 0) return null;
  const lastN = complete.slice(-minutes);
  return lastN.reduce((sum, p) => sum + p.rate_per_min, 0) / lastN.length;
}

/**
 * Displayed "muons per minute" — server-reconciled, pressure-corrected, stable.
 * Use this in the UI instead of the lossy rolling `muonStore.rate`.
 */
export const muonDisplayRate: Readable<number | null> = derived(muonStore, ($s) =>
  recentMeanRate($s.history, Math.floor(Date.now() / 1000)),
);

// Test-only: reset the rolling-60s event window. Production code never calls this.
export function _resetMuonRateWindow(): void {
  recentEventTimestamps = [];
  muonBuffer = [];
}
