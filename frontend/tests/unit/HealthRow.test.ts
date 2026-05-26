import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import HealthRow from '$lib/panels/HealthRow.svelte';
import type { SourceHealth } from '$lib/types';

const makeHealth = (): SourceHealth => ({
  last_event_ts: null,
  freshness: 'healthy',
  staleness_threshold_sec: 600,
  last_poll_status: null,
});

describe('HealthRow', () => {
  it('renders 9 status dots', () => {
    const { container } = render(HealthRow, {
      props: {
        health: {
          timestamp: 0,
          status: 'healthy',
          local: { weather: makeHealth(), muon: makeHealth() },
          external: {
            usgs: makeHealth(),
            emsc: makeHealth(),
            bgs: makeHealth(),
            noaa: makeHealth(),
            blitzortung: makeHealth(),
            aurora: makeHealth(),
          },
          pi: { temp_c: null, throttled: null, status: 'healthy', warnings: [] },
        },
        wsConnected: true,
      },
    });
    const dots = container.querySelectorAll('[data-role="status-dot"]');
    expect(dots).toHaveLength(9);
  });
});
