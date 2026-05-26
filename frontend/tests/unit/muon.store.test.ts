import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { muonStore, bufferMuonEvent, flushMuonBuffer } from '$lib/stores/muon';
import type { MuonEvent } from '$lib/types';

describe('muon store buffer', () => {
  beforeEach(() => {
    muonStore.set({ current: null, history: [], rate: null, lastUpdateTs: null });
  });

  it('buffers events and flushes them to store history', () => {
    const evt: MuonEvent = { ts: 1000, latest_event_ts: 1000, detector_pressure_hpa: null, detector_temp_c: null };
    bufferMuonEvent(evt);
    bufferMuonEvent(evt);
    bufferMuonEvent(evt);
    flushMuonBuffer();
    const state = get(muonStore);
    expect(state.history).toHaveLength(3);
  });
});
