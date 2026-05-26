import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';
import { muonStore, bufferMuonEvent, flushMuonBuffer, seedMuonHistory, _resetMuonRateWindow } from '$lib/stores/muon';
import type { MuonEvent } from '$lib/types';

describe('muon store buffer', () => {
  beforeEach(() => {
    muonStore.set({ current: null, history: [], rate: null, lastUpdateTs: null });
    _resetMuonRateWindow();
  });

  it('buffers events and flushes them to store history', () => {
    const nowSec = Math.floor(Date.now() / 1000);
    const evt: MuonEvent = { ts: nowSec, latest_event_ts: nowSec, detector_pressure_hpa: null, detector_temp_c: null };
    bufferMuonEvent(evt);
    bufferMuonEvent(evt);
    bufferMuonEvent(evt);
    flushMuonBuffer();
    const state = get(muonStore);
    expect(state.history).toHaveLength(3);
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

  it('history continues to extend with each flush', () => {
    const nowSec = Math.floor(Date.now() / 1000);
    bufferMuonEvent({ ts: nowSec - 10, latest_event_ts: nowSec - 10, detector_pressure_hpa: null, detector_temp_c: null });
    bufferMuonEvent({ ts: nowSec - 5, latest_event_ts: nowSec - 5, detector_pressure_hpa: null, detector_temp_c: null });
    flushMuonBuffer();
    bufferMuonEvent({ ts: nowSec, latest_event_ts: nowSec, detector_pressure_hpa: null, detector_temp_c: null });
    flushMuonBuffer();
    expect(get(muonStore).history).toHaveLength(3);
  });
});
