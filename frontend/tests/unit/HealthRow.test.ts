import { describe, it, expect, beforeEach } from 'vitest';
import { render } from '@testing-library/svelte';
import { get } from 'svelte/store';
import HealthRow from '$lib/panels/HealthRow.svelte';
import { healthStore } from '$lib/stores/health';
import { wsStatus } from '$lib/stores/ws';
import type { SourceHealth } from '$lib/types';

const makeHealth = (freshness: 'healthy' | 'stale' | 'down' = 'healthy'): SourceHealth => ({
  last_event_ts: Math.floor(Date.now() / 1000) - 30,
  freshness,
  staleness_threshold_sec: 600,
  last_poll_status: 'success',
});

const fullHealthData = {
  timestamp: Math.floor(Date.now() / 1000),
  status: 'healthy' as const,
  local: {
    weather: makeHealth(),
    muon:    makeHealth(),
  },
  external: {
    usgs:        makeHealth(),
    emsc:        makeHealth(),
    bgs:         makeHealth(),
    noaa:        makeHealth(),
    blitzortung: makeHealth(),
    aurora:      makeHealth(),
  },
  pi: { temp_c: null, throttled: null, status: 'healthy' as const, warnings: [] },
};

describe('HealthRow', () => {
  beforeEach(() => {
    healthStore.set({ data: fullHealthData, lastFetchTs: Math.floor(Date.now() / 1000) });
    wsStatus.set('connected');
  });

  it('renders 12 health entries', () => {
    const { container } = render(HealthRow);
    const entries = container.querySelectorAll('.health-entry');
    expect(entries).toHaveLength(12);
  });

  it('renders at least one green status dot', () => {
    const { container } = render(HealthRow);
    const greenDots = container.querySelectorAll('.status-green');
    expect(greenDots.length).toBeGreaterThan(0);
  });

  it('renders all expected source labels', () => {
    const { container } = render(HealthRow);
    const text = container.textContent ?? '';
    expect(text).toContain('Weather node');
    expect(text).toContain('Muon detector');
    expect(text).toContain('USGS');
    expect(text).toContain('EMSC');
    expect(text).toContain('BGS');
    expect(text).toContain('NOAA');
    expect(text).toContain('Lightning');
    expect(text).toContain('AuroraWatch');
    expect(text).toContain('Forecast');
    expect(text).toContain('Air quality');
    expect(text).toContain('NMDB');
    expect(text).toContain('Live updates');
  });
});
