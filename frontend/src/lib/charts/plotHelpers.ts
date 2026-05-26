import * as Plot from '@observablehq/plot';
import type { MuonPoint, WeatherPoint } from '$lib/types';

const WINDOW_SEC = 86400;
const STROKE_DATA = '#111111';
const STROKE_GRID = '#f0f0ec';
const FILL_DOT = '#6b8e6b';

/**
 * Centered rolling average over MuonPoint series.
 * Window shrinks symmetrically at the edges so output length matches input.
 * Exported for unit testing.
 */
export function rollingAverage(data: MuonPoint[], window: number): MuonPoint[] {
  if (data.length === 0) return [];
  const half = Math.floor(window / 2);
  return data.map((_, i) => {
    const lo = Math.max(0, i - half);
    const hi = Math.min(data.length - 1, i + half);
    let sum = 0;
    for (let j = lo; j <= hi; j++) sum += data[j].rate_per_min;
    return { ts: data[i].ts, rate_per_min: sum / (hi - lo + 1) };
  });
}

export function buildMuonPlot(data: MuonPoint[], width: number): SVGElement | HTMLElement {
  const now = Date.now();
  const start = new Date(now - WINDOW_SEC * 1000);
  const end = new Date(now);

  // Exclude the in-progress minute bucket so the right edge never shows a
  // sudden drop while the current minute is still filling.
  const nowSec = Math.floor(now / 1000);
  const currentMinuteStart = nowSec - (nowSec % 60);
  const completed = data.filter(p => p.ts < currentMinuteStart);

  // Smooth raw per-minute Poisson noise with a 5-point centered rolling average.
  const smoothed = rollingAverage(completed, 5);
  const last = smoothed.length > 0 ? smoothed[smoothed.length - 1] : null;

  return Plot.plot({
    width,
    height: 240,
    marginLeft: 60,
    marginRight: 20,
    marginBottom: 28,
    marginTop: 8,
    x: { type: 'time', domain: [start, end] },
    y: { label: null, grid: true, ticks: 4 },
    marks: [
      Plot.gridY({ stroke: STROKE_GRID, strokeWidth: 1 }),
      Plot.line(smoothed, {
        x: (d: MuonPoint) => new Date(d.ts * 1000),
        y: 'rate_per_min',
        stroke: STROKE_DATA,
        strokeWidth: 2,
        strokeLinejoin: 'round',
        strokeLinecap: 'round',
      }),
      ...(last
        ? [
            Plot.dot([last], {
              x: (d: MuonPoint) => new Date(d.ts * 1000),
              y: 'rate_per_min',
              fill: FILL_DOT,
              r: 5,
            }),
          ]
        : []),
    ],
  });
}

export function buildTempPlot(data: WeatherPoint[], width: number): SVGElement | HTMLElement {
  const now = Date.now();
  const start = new Date(now - WINDOW_SEC * 1000);
  const end = new Date(now);
  const valid = data.filter(p => p.temp_c != null);
  const last = valid.length > 0 ? valid[valid.length - 1] : null;

  return Plot.plot({
    width,
    height: 180,
    marginLeft: 60,
    marginRight: 20,
    marginBottom: 28,
    marginTop: 8,
    x: { type: 'time', domain: [start, end] },
    y: { label: null, grid: true, ticks: 3 },
    marks: [
      Plot.gridY({ stroke: STROKE_GRID, strokeWidth: 1 }),
      Plot.line(valid, {
        x: (d: WeatherPoint) => new Date(d.ts * 1000),
        y: (d: WeatherPoint) => d.temp_c,
        stroke: STROKE_DATA,
        strokeWidth: 2,
        strokeLinejoin: 'round',
        strokeLinecap: 'round',
      }),
      ...(last
        ? [
            Plot.dot([last], {
              x: (d: WeatherPoint) => new Date(d.ts * 1000),
              y: (d: WeatherPoint) => d.temp_c as number,
              fill: FILL_DOT,
              r: 5,
            }),
          ]
        : []),
    ],
  });
}
