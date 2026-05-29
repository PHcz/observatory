import { describe, it, expect, vi } from 'vitest';
import { buildHumidityDewpointPlot } from '$lib/charts/plotHelpers';
import * as dewpointMod from '$lib/utils/dewpoint';
import type { WeatherPoint } from '$lib/types';

describe('buildHumidityDewpointPlot', () => {
  it('is exported', () => {
    expect(typeof buildHumidityDewpointPlot).toBe('function');
  });

  it('renders two line paths (humidity + dewpoint)', () => {
    const points: WeatherPoint[] = Array.from({ length: 24 }, (_, i) => ({
      ts: 1700000000 + i * 3600,
      humidity_pct: 70 + Math.sin(i / 4) * 10,
      temp_c: 15 + Math.cos(i / 4) * 3,
    }));
    const result = buildHumidityDewpointPlot(points, 600) as SVGElement;
    const paths = result.querySelectorAll('path');
    expect(paths.length).toBeGreaterThanOrEqual(2);
  });

  it('computes dewpoint via dewPointC for every valid point', () => {
    const spy = vi.spyOn(dewpointMod, 'dewPointC');
    const points: WeatherPoint[] = Array.from({ length: 3 }, (_, i) => ({
      ts: 1700000000 + i,
      humidity_pct: 70,
      temp_c: 15,
    }));
    buildHumidityDewpointPlot(points, 600);
    expect(spy).toHaveBeenCalledTimes(3);
    spy.mockRestore();
  });
});
