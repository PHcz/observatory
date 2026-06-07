import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
// RED until Wave 5 (plan 13-05): the panel + muonAnalysis store do not exist yet,
// so this import fails RED exactly as intended.
import AdcSpectrumPanel from '$lib/panels/AdcSpectrumPanel.svelte';
import { setMuonAnalysis } from '$lib/stores/muonAnalysis';
import { settingsStore } from '$lib/stores/settings';

beforeEach(() => {
  settingsStore.resetToDefaults();
});

describe('AdcSpectrumPanel (RED until Wave 5)', () => {
  it('shows the locked empty-state heading when there is no muon data', async () => {
    render(AdcSpectrumPanel);
    setMuonAnalysis(null);
    await tick();
    expect(screen.getByText(/No muon data yet/i)).toBeTruthy();
  });

  it('shows the ADC SPECTRUM section title', () => {
    render(AdcSpectrumPanel);
    expect(screen.getByText('ADC SPECTRUM')).toBeTruthy();
  });

  it('renders the histogram when analysis data is present', async () => {
    render(AdcSpectrumPanel);
    setMuonAnalysis({
      adc_histogram: [
        { bin_center: 320, count: 12 },
        { bin_center: 340, count: 28 },
      ],
      barometric: null,
      raw_uncorrected: true,
    });
    await tick();
    expect(screen.queryByText(/No muon data yet/i)).toBeNull();
  });

  it('renders the chart container unconditionally, even before data', () => {
    const { container } = render(AdcSpectrumPanel);
    // Mount-bug regression: the bind:this container must exist at mount so the
    // reactive build re-runs once data arrives (mirrors MuonChart).
    expect(container.querySelector('[data-chart="adc-spectrum"]')).toBeTruthy();
  });

  it('mounts an <svg> into the container once histogram data arrives', async () => {
    const { container } = render(AdcSpectrumPanel);
    setMuonAnalysis({
      adc_histogram: [
        { bin_center: 320, count: 12 },
        { bin_center: 340, count: 28 },
      ],
      barometric: null,
      raw_uncorrected: true,
    });
    await tick();
    const host = container.querySelector('[data-chart="adc-spectrum"]');
    expect(host).toBeTruthy();
    expect(host?.querySelector('svg')).toBeTruthy();
  });
});
