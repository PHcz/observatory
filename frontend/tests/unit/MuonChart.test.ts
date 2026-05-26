import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render } from '@testing-library/svelte';
import MuonChart from '$lib/panels/MuonChart.svelte';

const mockFetchResponse = {
  ok: true,
  json: async () => ({
    window: { from: 0, to: 0 },
    bucket_size_sec: 60,
    agg: 'minute',
    rows: [],
  }),
};

describe('MuonChart', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockFetchResponse));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders a div with data-chart="muon"', () => {
    const { container } = render(MuonChart);
    expect(container.querySelector('[data-chart="muon"]')).toBeTruthy();
  });

  it('data-chart="muon" container is present after mount', async () => {
    const { container } = render(MuonChart);
    // Allow microtask queue to flush
    await new Promise(r => setTimeout(r, 0));
    const chart = container.querySelector('[data-chart="muon"]');
    expect(chart).not.toBeNull();
  });
});
