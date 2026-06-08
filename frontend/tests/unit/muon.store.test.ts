import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';
import { muonStore, bufferMuonEvent, flushMuonBuffer, seedMuonHistory, setMuonSnapshot, _resetMuonRateWindow } from '$lib/stores/muon';
import type { MuonEvent } from '$lib/types';

describe('muon store buffer', () => {
  beforeEach(() => {
    muonStore.set({ current: null, history: [], rate: null, lastUpdateTs: null });
    _resetMuonRateWindow();
  });

  it('buffers events and flushes them into a single minute bucket (07-22: bucket-aggregation)', () => {
    const nowSec = Math.floor(Date.now() / 1000);
    const evt: MuonEvent = { ts: nowSec, latest_event_ts: nowSec, detector_pressure_hpa: null, detector_temp_c: null };
    bufferMuonEvent(evt);
    bufferMuonEvent(evt);
    bufferMuonEvent(evt);
    flushMuonBuffer();
    const state = get(muonStore);
    // Three events at the same ts collapse to one bucket entry with count=3
    expect(state.history).toHaveLength(1);
    expect(state.history[0].rate_per_min).toBe(3);
  });

  it('flush preserves Phase-16 fields on REST-seeded rows (ENH-01/02)', () => {
    // Regression: flushMuonBuffer rebuilt every history row as {ts, rate_per_min},
    // stripping flux_cm2_min / Poisson band / anomaly fields on the first live
    // WS tick — so the rate chart's annotation, band, and dots went inert.
    const nowSec = Math.floor(Date.now() / 1000);
    const seededTs = nowSec - 3600; // within 24h, distinct from the live bucket
    seedMuonHistory([
      {
        ts: seededTs,
        rate_per_min: 104.15,
        flux_cm2_min: 4.166,
        lower_1sigma: 95.7,
        upper_1sigma: 116.3,
        anomaly_z: -6.19,
        anomaly_severity: 'alert',
      },
    ]);

    // A live event in a different (current) bucket triggers the merge/rebuild.
    const liveEvt: MuonEvent = { ts: nowSec, latest_event_ts: nowSec, detector_pressure_hpa: null, detector_temp_c: null };
    bufferMuonEvent(liveEvt);
    flushMuonBuffer();

    const state = get(muonStore);
    const seeded = state.history.find(p => p.ts === seededTs);
    expect(seeded).toBeDefined();
    expect(seeded?.flux_cm2_min).toBe(4.166);
    expect(seeded?.lower_1sigma).toBe(95.7);
    expect(seeded?.upper_1sigma).toBe(116.3);
    expect(seeded?.anomaly_severity).toBe('alert');
  });

  it('flush with no buffered events is a no-op', () => {
    flushMuonBuffer();
    const state = get(muonStore);
    expect(state.history).toHaveLength(0);
  });

  it('flush drops events older than 24h (86400s)', () => {
    const nowSec = Math.floor(Date.now() / 1000);
    const staleTs = nowSec - 90000; // 90000s > 86400s
    const staleEvt: MuonEvent = { ts: staleTs, latest_event_ts: staleTs, detector_pressure_hpa: null, detector_temp_c: null };

    // Seed history with 5 stale points
    seedMuonHistory([
      { ts: staleTs - 100, rate_per_min: 1 },
      { ts: staleTs - 200, rate_per_min: 2 },
      { ts: staleTs - 300, rate_per_min: 3 },
      { ts: staleTs - 400, rate_per_min: 4 },
      { ts: staleTs - 500, rate_per_min: 5 },
    ]);

    // Buffer and flush a stale event
    bufferMuonEvent(staleEvt);
    flushMuonBuffer();

    const state = get(muonStore);
    // All points (5 seeded + 1 flushed) are older than 24h so they should be filtered out
    expect(state.history).toHaveLength(0);
  });

  it('flush keeps events within 24h window', () => {
    const nowSec = Math.floor(Date.now() / 1000);
    const recentTs = nowSec - 3600; // 1h ago — within 24h
    const recentEvt: MuonEvent = { ts: recentTs, latest_event_ts: recentTs, detector_pressure_hpa: null, detector_temp_c: null };
    bufferMuonEvent(recentEvt);
    flushMuonBuffer();
    const state = get(muonStore);
    expect(state.history).toHaveLength(1);
  });

  it('computes live rate from rolling 60s event count on flush', () => {
    const nowSec = Math.floor(Date.now() / 1000);
    // Buffer 30 events, all within the last 60s
    for (let i = 0; i < 30; i++) {
      const ts = nowSec - (i % 60); // all within [nowSec-59 .. nowSec]
      bufferMuonEvent({ ts, latest_event_ts: ts, detector_pressure_hpa: null, detector_temp_c: null });
    }
    flushMuonBuffer();
    expect(get(muonStore).rate).toBe(30);
  });

  it('expires events older than 60s from rolling rate window', () => {
    vi.useFakeTimers();
    try {
      const startMs = 1_700_000_000_000;
      vi.setSystemTime(startMs);
      const startSec = Math.floor(startMs / 1000);

      // First flush: 30 events all within last 60s
      for (let i = 0; i < 30; i++) {
        const ts = startSec - (i % 60);
        bufferMuonEvent({ ts, latest_event_ts: ts, detector_pressure_hpa: null, detector_temp_c: null });
      }
      flushMuonBuffer();
      expect(get(muonStore).rate).toBe(30);

      // Advance time by 120s; buffer 5 fresh events
      vi.setSystemTime(startMs + 120_000);
      const nowSec2 = Math.floor((startMs + 120_000) / 1000);
      for (let i = 0; i < 5; i++) {
        const ts = nowSec2 - i;
        bufferMuonEvent({ ts, latest_event_ts: ts, detector_pressure_hpa: null, detector_temp_c: null });
      }
      flushMuonBuffer();
      // Old 30 events are now >60s old; only the 5 fresh ones count
      expect(get(muonStore).rate).toBe(5);
    } finally {
      vi.useRealTimers();
    }
  });

  it('flush with no buffered events leaves rate unchanged', () => {
    muonStore.set({ current: null, history: [], rate: 77, lastUpdateTs: null });
    flushMuonBuffer();
    expect(get(muonStore).rate).toBe(77);
  });
});

describe('flushMuonBuffer — minute-bucket aggregation', () => {
  beforeEach(() => {
    muonStore.set({ current: null, history: [], rate: null, lastUpdateTs: null });
    _resetMuonRateWindow();
  });

  it('two events in the SAME minute produce ONE history entry with count=2', () => {
    vi.useFakeTimers();
    try {
      // Fix wall-clock so plan-spec timestamps (1716800000) survive the 24h trim
      vi.setSystemTime(1716800100 * 1000);
      // Both ts fall in bucket Math.floor(1716800000/60)*60 = 1716799980
      bufferMuonEvent({ ts: 1716800000, latest_event_ts: 1716800000, detector_pressure_hpa: null, detector_temp_c: null });
      bufferMuonEvent({ ts: 1716800030, latest_event_ts: 1716800030, detector_pressure_hpa: null, detector_temp_c: null });
      flushMuonBuffer();
      const state = get(muonStore);
      expect(state.history).toHaveLength(1);
      expect(state.history[0].ts).toBe(1716799980);
      expect(state.history[0].rate_per_min).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it('five events spanning TWO minutes produce TWO history entries (not five)', () => {
    vi.useFakeTimers();
    try {
      vi.setSystemTime(1716800100 * 1000);
      // bucket 1716799980: ts 1716800010, 1716800020, 1716800030 (count 3)
      // bucket 1716800040: ts 1716800070, 1716800080 (count 2)
      bufferMuonEvent({ ts: 1716800010, latest_event_ts: 1716800010, detector_pressure_hpa: null, detector_temp_c: null });
      bufferMuonEvent({ ts: 1716800020, latest_event_ts: 1716800020, detector_pressure_hpa: null, detector_temp_c: null });
      bufferMuonEvent({ ts: 1716800030, latest_event_ts: 1716800030, detector_pressure_hpa: null, detector_temp_c: null });
      bufferMuonEvent({ ts: 1716800070, latest_event_ts: 1716800070, detector_pressure_hpa: null, detector_temp_c: null });
      bufferMuonEvent({ ts: 1716800080, latest_event_ts: 1716800080, detector_pressure_hpa: null, detector_temp_c: null });
      flushMuonBuffer();
      const state = get(muonStore);
      expect(state.history).toHaveLength(2);
      expect(state.history[0]).toEqual({ ts: 1716799980, rate_per_min: 3 });
      expect(state.history[1]).toEqual({ ts: 1716800040, rate_per_min: 2 });
    } finally {
      vi.useRealTimers();
    }
  });

  it('event for an existing bucket increments the existing entry', () => {
    vi.useFakeTimers();
    try {
      vi.setSystemTime(1716800100 * 1000);
      seedMuonHistory([{ ts: 1716799980, rate_per_min: 5 }]);
      // ts 1716800010 → bucket 1716799980 (same as seeded)
      bufferMuonEvent({ ts: 1716800010, latest_event_ts: 1716800010, detector_pressure_hpa: null, detector_temp_c: null });
      flushMuonBuffer();
      const state = get(muonStore);
      expect(state.history).toHaveLength(1);
      expect(state.history[0].rate_per_min).toBe(6);
    } finally {
      vi.useRealTimers();
    }
  });

  it('state.rate still equals the rolling-60s event count after bucket rework', () => {
    vi.useFakeTimers();
    try {
      const nowMs = 1716800100 * 1000;
      vi.setSystemTime(nowMs);
      // 3 events within last 60s of now=1716800100
      bufferMuonEvent({ ts: 1716800050, latest_event_ts: 1716800050, detector_pressure_hpa: null, detector_temp_c: null });
      bufferMuonEvent({ ts: 1716800070, latest_event_ts: 1716800070, detector_pressure_hpa: null, detector_temp_c: null });
      bufferMuonEvent({ ts: 1716800090, latest_event_ts: 1716800090, detector_pressure_hpa: null, detector_temp_c: null });
      // 1 event older than 60s window (1716800100 - 60 = 1716800040; 1716800010 < that)
      bufferMuonEvent({ ts: 1716800010, latest_event_ts: 1716800010, detector_pressure_hpa: null, detector_temp_c: null });
      flushMuonBuffer();
      expect(get(muonStore).rate).toBe(3);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('muon bootstrap rate (UI-13)', () => {
  beforeEach(() => {
    muonStore.set({ current: null, history: [], rate: null, lastUpdateTs: null });
    _resetMuonRateWindow();
  });

  it('seeds rate from REST snapshot rate_per_min', () => {
    setMuonSnapshot({ ts: 1716908400, rate_per_min: 87 } as any);
    expect(get(muonStore).rate).toBe(87);
  });

  it('handles null snapshot', () => {
    setMuonSnapshot(null);
    expect(get(muonStore).rate).toBeNull();
  });

  it('handles missing rate_per_min field', () => {
    setMuonSnapshot({ ts: 1716908400 } as any);
    expect(get(muonStore).rate).toBeNull();
  });
});
