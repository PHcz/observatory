import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render } from '@testing-library/svelte';
import TemperatureChart from '$lib/panels/TemperatureChart.svelte';

const mockFetchResponse = {
  ok: true,
  json: async () => ({
    window: { from: 0, to: 0 },
    bucket_size_sec: 60,
    agg: 'minute',
    rows: [],
  }),
};

describe('TemperatureChart', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockFetchResponse));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders a div with data-chart="temperature"', () => {
    const { container } = render(TemperatureChart);
    expect(container.querySelector('[data-chart="temperature"]')).toBeTruthy();
  });

  it('data-chart="temperature" container is present after mount', async () => {
    const { container } = render(TemperatureChart);
    await new Promise(r => setTimeout(r, 0));
    const chart = container.querySelector('[data-chart="temperature"]');
    expect(chart).not.toBeNull();
  });
});
