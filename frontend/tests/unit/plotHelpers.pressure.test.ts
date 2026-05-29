import { describe, it, expect, vi } from 'vitest';
import { buildPressurePlot } from '$lib/charts/plotHelpers';
import type { WeatherPoint } from '$lib/types';

describe('buildPressurePlot', () => {
  it('is exported as a function', () => {
    expect(typeof buildPressurePlot).toBe('function');
  });

  it('returns an SVGElement for empty input', () => {
    const result = buildPressurePlot([], 600);
    expect(result).toBeTruthy();
  });

  it('renders dual-layer (raw + smoothed) when given data', () => {
    const points: WeatherPoint[] = Array.from({ length: 24 }, (_, i) => ({
      ts: 1700000000 + i * 3600,
      pressure_hpa: 1010 + Math.sin(i / 4) * 5,
    }));
    const result = buildPressurePlot(points, 600) as SVGElement;
    const paths = result.querySelectorAll('path');
    expect(paths.length).toBeGreaterThanOrEqual(2);
  });

  it('reads --chart-data from getComputedStyle', () => {
    const spy = vi.spyOn(window, 'getComputedStyle');
    buildPressurePlot([], 600);
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });
});
