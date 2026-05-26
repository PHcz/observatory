import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';
import { muonStore, bufferMuonEvent, flushMuonBuffer, seedMuonHistory } from '$lib/stores/muon';
import type { MuonEvent } from '$lib/types';

describe('muon store buffer', () => {
  beforeEach(() => {
    muonStore.set({ current: null, history: [], rate: null, lastUpdateTs: null });
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

  it('updates rate from last flushed event', () => {
    const nowSec = Math.floor(Date.now() / 1000);
    // Create an event-like object with rate_per_min (as the flush code casts it)
    const evt = { ts: nowSec, latest_event_ts: nowSec, detector_pressure_hpa: null, detector_temp_c: null, rate_per_min: 42 } as unknown as MuonEvent;
    bufferMuonEvent(evt);
    flushMuonBuffer();
    expect(get(muonStore).rate).toBe(42);
  });
});
