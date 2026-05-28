import * as Plot from '@observablehq/plot';
import type { MuonPoint, WeatherPoint } from '$lib/types';
import { loess } from '$lib/charts/loess';
import { paddedYDomain } from '$lib/charts/domain';

const WINDOW_SEC = 86400;
const STROKE_DATA = '#111111';
const STROKE_GRID = '#f0f0ec';
const FILL_DOT = '#6b8e6b';

/**
 * Filter out muon points whose ts is within the last 90 seconds of wall-clock time.
 * Guards the right edge of the chart against client/server clock skew and
 * backend aggregation lag (the most recent minute can still be filling).
 * Exported for unit testing.
 *
 * Predicate: a point is KEPT iff (nowMs - p.ts * 1000) >= 90_000 — i.e. its
 * timestamp is at least 90 seconds old. Boundary is inclusive (exactly 90s old
 * is kept; 89s old is dropped).
 */
export function withinSafetyMargin(data: MuonPoint[], nowMs: number = Date.now()): MuonPoint[] {
  return data.filter(p => (nowMs - p.ts * 1000) >= 90_000);
}

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

  // Exclude any point within the last 90 seconds of wall-clock time.
  // Belt-and-braces against client/server clock skew and the still-filling
  // current minute bucket (UAT gap 4 round 2).
  const safe = withinSafetyMargin(data, now);

  // UI-13: dual-layer rendering. Raw 1-minute points in light grey behind,
  // LOESS-smoothed line (span=0.15) on top. Pitfall 2: marks array order
  // determines z-order, so raw line MUST come before smoothed line.
  const rawYs = safe.map(p => p.rate_per_min);
  const smoothedYs = loess(rawYs, 0.15);
  const smoothed: MuonPoint[] = safe.map((p, i) => ({ ts: p.ts, rate_per_min: smoothedYs[i] }));
  const last = smoothed.length > 0 ? smoothed[smoothed.length - 1] : null;
  const domain = paddedYDomain([...rawYs, ...smoothedYs]);

  return Plot.plot({
    width,
    height: 240,
    marginLeft: 60,
    marginRight: 20,
    marginBottom: 28,
    marginTop: 8,
    x: { type: 'time', domain: [start, end] },
    y: { label: null, grid: true, ticks: 4, ...(domain ? { domain } : {}) },
    marks: [
      Plot.gridY({ stroke: STROKE_GRID, strokeWidth: 1 }),
      // Raw line — BEHIND smoothed (array order = z-order; Pitfall 2)
      Plot.line(safe, {
        x: (d: MuonPoint) => new Date(d.ts * 1000),
        y: 'rate_per_min',
        stroke: '#cccccc',
        strokeWidth: 0.5,
        strokeOpacity: 0.4,
      }),
      // Smoothed line — on top
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

  // UI-13: dual-layer rendering mirrors buildMuonPlot (see 08-01 SUMMARY).
  // Filter null temps first (sensor failure), then LOESS-smooth (span 0.15).
  // paddedYDomain handles negative winter temps correctly (5% padding both sides).
  const valid = data.filter(p => p.temp_c != null);
  const rawYs = valid.map(p => p.temp_c as number);
  const smoothedYs = loess(rawYs, 0.15);
  const smoothed: WeatherPoint[] = valid.map((p, i) => ({ ts: p.ts, temp_c: smoothedYs[i] }));
  const last = smoothed.length > 0 ? smoothed[smoothed.length - 1] : null;
  const domain = paddedYDomain([...rawYs, ...smoothedYs]);

  return Plot.plot({
    width,
    height: 180,
    marginLeft: 60,
    marginRight: 20,
    marginBottom: 28,
    marginTop: 8,
    x: { type: 'time', domain: [start, end] },
    y: { label: null, grid: true, ticks: 3, ...(domain ? { domain } : {}) },
    marks: [
      Plot.gridY({ stroke: STROKE_GRID, strokeWidth: 1 }),
      // Raw line — BEHIND smoothed (array order = z-order; Pitfall 2 from 08-RESEARCH)
      Plot.line(valid, {
        x: (d: WeatherPoint) => new Date(d.ts * 1000),
        y: (d: WeatherPoint) => d.temp_c as number,
        stroke: '#cccccc',
        strokeWidth: 0.5,
        strokeOpacity: 0.4,
      }),
      // Smoothed line — on top
      Plot.line(smoothed, {
        x: (d: WeatherPoint) => new Date(d.ts * 1000),
        y: (d: WeatherPoint) => d.temp_c as number,
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
