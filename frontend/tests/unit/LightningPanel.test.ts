import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { lightningStore } from '$lib/stores/lightning';
import LightningPanel from '$lib/panels/LightningPanel.svelte';

describe('LightningPanel', () => {
  beforeEach(() => {
    lightningStore.set({ summary: null, hourlyBuckets: [], lastUpdateTs: null });
  });

  it('shows empty state when summary is null', () => {
    render(LightningPanel);
    expect(screen.getByText('No strikes in the last 24h.')).toBeTruthy();
  });

  it('shows empty state when past_24h is 0', () => {
    lightningStore.set({
      summary: { past_hour: 0, past_24h: 0, nearest_km: null, total_today: 0, ts: 1000 },
      hourlyBuckets: new Array(24).fill(0),
      lastUpdateTs: 1000,
    });
    render(LightningPanel);
    expect(screen.getByText('No strikes in the last 24h.')).toBeTruthy();
  });

  it('shows section title "Lightning"', () => {
    render(LightningPanel);
    expect(screen.getByText('Lightning')).toBeTruthy();
  });

  it('shows metric labels when data is present', () => {
    lightningStore.set({
      summary: { past_hour: 3, past_24h: 12, nearest_km: 42, total_today: 12, ts: 1000 },
      hourlyBuckets: new Array(24).fill(0),
      lastUpdateTs: 1000,
    });
    render(LightningPanel);
    expect(screen.getByText('Past hour')).toBeTruthy();
    expect(screen.getByText('Past 24h')).toBeTruthy();
    expect(screen.getByText('Nearest today')).toBeTruthy();
  });

  it('shows past_24h count when data is present', () => {
    lightningStore.set({
      summary: { past_hour: 3, past_24h: 12, nearest_km: 42, total_today: 12, ts: 1000 },
      hourlyBuckets: new Array(24).fill(0),
      lastUpdateTs: 1000,
    });
    render(LightningPanel);
    expect(screen.getByText('12')).toBeTruthy();
  });

  it('shows nearest_km when non-null', () => {
    lightningStore.set({
      summary: { past_hour: 3, past_24h: 12, nearest_km: 42, total_today: 12, ts: 1000 },
      hourlyBuckets: new Array(24).fill(0),
      lastUpdateTs: 1000,
    });
    render(LightningPanel);
    expect(screen.getByText('42')).toBeTruthy();
  });

  it('shows em-dash for nearest_km when null', () => {
    lightningStore.set({
      summary: { past_hour: 3, past_24h: 12, nearest_km: null, total_today: 12, ts: 1000 },
      hourlyBuckets: new Array(24).fill(0),
      lastUpdateTs: 1000,
    });
    const { container } = render(LightningPanel);
    expect(container.querySelector('.nearest-value')?.textContent).toBe('—');
  });

  it('does not show empty state text when data has strikes', () => {
    lightningStore.set({
      summary: { past_hour: 3, past_24h: 12, nearest_km: 42, total_today: 12, ts: 1000 },
      hourlyBuckets: new Array(24).fill(0),
      lastUpdateTs: 1000,
    });
    render(LightningPanel);
    expect(screen.queryByText('No strikes in the last 24h.')).toBeNull();
  });

  // Legacy prop-based test preserved for compatibility
  it('shows no-strikes copy when past_24h=0 (legacy prop test)', () => {
    lightningStore.set({
      summary: { past_hour: 0, past_24h: 0, nearest_km: null, total_today: 0, ts: 1000 },
      hourlyBuckets: [],
      lastUpdateTs: 1000,
    });
    render(LightningPanel);
    expect(screen.getByText('No strikes in the last 24h.')).toBeTruthy();
  });
});
