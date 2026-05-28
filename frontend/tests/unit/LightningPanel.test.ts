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

  // UI-15 sparkline backend wiring (folded from 08-07)
  it('renders 24 bars from summary.hourly_buckets, proportional heights', () => {
    lightningStore.set({
      summary: {
        past_hour: 0, past_24h: 5, nearest_km: null, total_today: 5, ts: 1000,
        // max is 2 at index 2 → bar[2] height == 80, bar[0] height == 40, zeros == 0
        hourly_buckets: [1, 0, 2, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
      },
      hourlyBuckets: [],  // intentionally empty — sparkline must read summary, not state-level
      lastUpdateTs: 1000,
    });
    const { container } = render(LightningPanel);
    const bars = container.querySelectorAll('svg.sparkline-svg rect');
    expect(bars.length).toBe(24);
    const h0 = parseFloat(bars[0].getAttribute('height') ?? '0');
    const h2 = parseFloat(bars[2].getAttribute('height') ?? '0');
    const h1 = parseFloat(bars[1].getAttribute('height') ?? '0');
    // max-bucket bar reaches full 80px viewBox height
    expect(h2).toBe(80);
    // bucket=1 → 1/2 * 80 = 40
    expect(h0).toBe(40);
    // bucket=0 → 0
    expect(h1).toBe(0);
  });

  it('renders 24 bars even when summary.hourly_buckets is absent (fallback zeros)', () => {
    lightningStore.set({
      summary: { past_hour: 0, past_24h: 5, nearest_km: null, total_today: 5, ts: 1000 },
      hourlyBuckets: [],
      lastUpdateTs: 1000,
    });
    const { container } = render(LightningPanel);
    const bars = container.querySelectorAll('svg.sparkline-svg rect');
    expect(bars.length).toBe(24);
  });

  it('scales bar heights against max(buckets, 1) (no divide-by-zero)', () => {
    lightningStore.set({
      summary: {
        past_hour: 0, past_24h: 0, nearest_km: null, total_today: 1, ts: 1000,
        // total_today=1 so the panel renders the metrics-row block
        // past_24h=0 here would trip the isEmpty guard; use total_today and bypass via past_24h=1
        hourly_buckets: new Array(24).fill(0),
      },
      hourlyBuckets: [],
      lastUpdateTs: 1000,
    });
    // Override past_24h so panel renders sparkline (not empty state)
    lightningStore.update(s => ({
      ...s,
      summary: { ...s.summary!, past_24h: 1 },
    }));
    const { container } = render(LightningPanel);
    const bars = container.querySelectorAll('svg.sparkline-svg rect');
    expect(bars.length).toBe(24);
    // All zeros — every bar has height 0, no exception thrown
    bars.forEach(bar => {
      const h = parseFloat(bar.getAttribute('height') ?? '0');
      expect(h).toBe(0);
    });
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
