import { describe, it, expect, vi } from 'vitest';
import { buildLightPlot } from '$lib/charts/plotHelpers';
import * as loessMod from '$lib/charts/loess';
import type { WeatherPoint } from '$lib/types';

describe('buildLightPlot', () => {
  it('is exported', () => {
    expect(typeof buildLightPlot).toBe('function');
  });

  it('clamps lux <= 0 to 1 before log10', () => {
    const spy = vi.spyOn(loessMod, 'loess');
    const points: WeatherPoint[] = [
      { ts: 1700000000, lux: 0 },
      { ts: 1700000001, lux: -5 },
      { ts: 1700000002, lux: 100 },
    ];
    buildLightPlot(points, 600);
    const firstCall = spy.mock.calls[0];
    expect(firstCall[0]).toEqual([0, 0, 2]);
    spy.mockRestore();
  });

  it('uses log scale on Y axis', () => {
    const points: WeatherPoint[] = Array.from({ length: 24 }, (_, i) => ({
      ts: 1700000000 + i * 3600,
      lux: Math.pow(10, 1 + Math.random() * 3),
    }));
    const result = buildLightPlot(points, 600) as SVGElement;
    const ticks = result.querySelectorAll('text');
    const labels = Array.from(ticks).map((t) => t.textContent || '');
    const decadeMatch = labels.some((l) => /^(10|100|1000|10k|10,000)$/.test(l));
    expect(decadeMatch).toBe(true);
  });
});
