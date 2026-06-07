import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
// RED until Wave 5 (plan 13-05): the panel + muonAnalysis store do not exist yet.
import BarometricPanel from '$lib/panels/BarometricPanel.svelte';
import { setMuonAnalysis } from '$lib/stores/muonAnalysis';
import { settingsStore } from '$lib/stores/settings';

beforeEach(() => {
  settingsStore.resetToDefaults();
});

describe('BarometricPanel (RED until Wave 5)', () => {
  it('shows the locked empty-state heading when there is no muon data', async () => {
    render(BarometricPanel);
    setMuonAnalysis(null);
    await tick();
    expect(screen.getByText(/No muon data yet/i)).toBeTruthy();
  });

  it('shows the BAROMETRIC COEFFICIENT section title', () => {
    render(BarometricPanel);
    expect(screen.getByText('BAROMETRIC COEFFICIENT')).toBeTruthy();
  });

  it('renders the β stat block when a fit is present', async () => {
    render(BarometricPanel);
    setMuonAnalysis({
      adc_histogram: [],
      barometric: { beta: -0.18, r_squared: 0.4, p_value: 0.02, n: 168 },
      raw_uncorrected: true,
    });
    await tick();
    // β stat card carries the COEFFICIENT label per UI-SPEC §Barometric stat cards.
    expect(screen.getByText(/COEFFICIENT/i)).toBeTruthy();
  });

  it('renders the chart container unconditionally, even before data', () => {
    const { container } = render(BarometricPanel);
    // Mount-bug regression: container present at mount (mirrors MuonChart).
    expect(container.querySelector('[data-chart="barometric"]')).toBeTruthy();
  });

  it('mounts an <svg> with scatter points once a fit + points arrive', async () => {
    const { container } = render(BarometricPanel);
    setMuonAnalysis({
      adc_histogram: [],
      barometric: {
        beta: -0.18,
        r_squared: 0.4,
        p_value: 0.02,
        n: 3,
        points: [
          { pressure_hpa: 1000, rate_per_min: 0.66 },
          { pressure_hpa: 1004, rate_per_min: 0.6 },
          { pressure_hpa: 1008, rate_per_min: 0.55 },
        ],
      },
      raw_uncorrected: true,
    });
    await tick();
    const host = container.querySelector('[data-chart="barometric"]');
    expect(host).toBeTruthy();
    expect(host?.querySelector('svg')).toBeTruthy();
  });
});
