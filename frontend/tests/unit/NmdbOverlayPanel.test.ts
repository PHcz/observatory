import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
// RED until Wave 5 (plan 13-05): the panel + nmdb store do not exist yet.
import NmdbOverlayPanel from '$lib/panels/NmdbOverlayPanel.svelte';
import { setNmdb } from '$lib/stores/nmdb';
import { settingsStore } from '$lib/stores/settings';

beforeEach(() => {
  settingsStore.resetToDefaults();
});

describe('NmdbOverlayPanel (RED until Wave 5)', () => {
  it('shows the locked cosmic-ray empty-state heading when no NMDB data', async () => {
    render(NmdbOverlayPanel);
    setNmdb(null);
    await tick();
    expect(screen.getByText(/Cosmic-ray reference not available yet/i)).toBeTruthy();
  });

  it('shows the COSMIC RAY OVERLAY section title', () => {
    render(NmdbOverlayPanel);
    expect(screen.getByText('COSMIC RAY OVERLAY')).toBeTruthy();
  });

  it('renders the overlay when NMDB + local series are present', async () => {
    const now = Math.floor(Date.now() / 1000);
    render(NmdbOverlayPanel);
    setNmdb({
      series: [{ ts: now, counts_per_sec: 100, pct_baseline: 100 }],
      local: [{ ts: now, rate_per_min: 60, pct_baseline: 100 }],
      baseline_window_days: 7,
      fetched_at: now,
    });
    await tick();
    expect(screen.queryByText(/Cosmic-ray reference not available yet/i)).toBeNull();
  });
});
