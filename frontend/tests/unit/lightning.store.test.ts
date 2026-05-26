import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { lightningStore, setLightning } from '$lib/stores/lightning';
import type { LightningSummary } from '$lib/types';

describe('lightning store setLightning', () => {
  beforeEach(() => {
    lightningStore.set({ summary: null, hourlyBuckets: [], lastUpdateTs: null });
  });

  it('stores a full snapshot summary as-is (no prior summary)', () => {
    const data: LightningSummary = {
      past_hour: 10051,
      past_24h: 35045,
      nearest_km: 65.4,
      total_today: 35045,
      ts: 1748290000,
    };
    setLightning(data);
    const s = get(lightningStore).summary;
    expect(s).not.toBeNull();
    expect(s!.past_hour).toBe(10051);
    expect(s!.past_24h).toBe(35045);
    expect(s!.nearest_km).toBe(65.4);
    expect(s!.total_today).toBe(35045);
    expect(s!.ts).toBe(1748290000);
  });

  it('merges a partial per-event frame into prior aggregates', () => {
    const snap: LightningSummary = {
      past_hour: 10051,
      past_24h: 35045,
      nearest_km: 65.4,
      total_today: 35045,
      ts: 1748290000,
    };
    setLightning(snap);
    // simulate a partial per-event frame
    setLightning({ nearest_km: 12.3, ts: 1748290060 } as Partial<LightningSummary> as LightningSummary);
    const s = get(lightningStore).summary;
    expect(s).not.toBeNull();
    expect(s!.past_hour).toBe(10051);
    expect(s!.past_24h).toBe(35045);
    expect(s!.total_today).toBe(35045);
    expect(s!.nearest_km).toBe(12.3);
    expect(s!.ts).toBe(1748290060);
  });

  it('accepts a partial frame on an empty store without dropping the partial fields', () => {
    setLightning({ ts: 1, nearest_km: null } as Partial<LightningSummary> as LightningSummary);
    const s = get(lightningStore).summary;
    expect(s).not.toBeNull();
    expect(s!.ts).toBe(1);
    expect(s!.nearest_km).toBeNull();
  });

  it('preserves hourlyBuckets across setLightning calls', () => {
    const buckets = new Array(24).fill(0).map((_, i) => i);
    lightningStore.set({ summary: null, hourlyBuckets: buckets, lastUpdateTs: null });
    const snap: LightningSummary = {
      past_hour: 10,
      past_24h: 100,
      nearest_km: 5,
      total_today: 100,
      ts: 1748290000,
    };
    setLightning(snap);
    const state = get(lightningStore);
    expect(state.hourlyBuckets).toEqual(buckets);
  });

  it('updates lastUpdateTs on each call', () => {
    expect(get(lightningStore).lastUpdateTs).toBeNull();
    setLightning({ ts: 1, nearest_km: null } as Partial<LightningSummary> as LightningSummary);
    const after = get(lightningStore).lastUpdateTs;
    expect(after).not.toBeNull();
    expect(typeof after).toBe('number');
  });
});
