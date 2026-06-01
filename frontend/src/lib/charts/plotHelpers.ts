import * as Plot from '@observablehq/plot';
import type { MuonPoint, WeatherPoint } from '$lib/types';
import { loess } from '$lib/charts/loess';
import { niceFloorDomain } from '$lib/charts/domain';
import { dewPointC } from '$lib/utils/dewpoint';

const WINDOW_SEC = 86400;

/**
 * Read theme tokens from CSS custom properties at render time.
 * MUST be called inside every build*Plot function (not module-scope) so
 * theme swaps via themeStore subscription pick up new values on next render.
 */
function tokens() {
  if (typeof document === 'undefined') {
    // SSR/test fallback — defaults match light theme
    return {
      raw: '#cccccc',
      data: '#111111',
      grid: '#f0f0ec',
      marker: '#6b8e6b',
      dewpoint: '#6b8e6b',
    };
  }
  const cs = getComputedStyle(document.documentElement);
  return {
    raw: cs.getPropertyValue('--chart-raw').trim() || '#cccccc',
    data: cs.getPropertyValue('--chart-data').trim() || '#111111',
    grid: cs.getPropertyValue('--chart-grid').trim() || '#f0f0ec',
    marker: cs.getPropertyValue('--chart-marker').trim() || '#6b8e6b',
    dewpoint: cs.getPropertyValue('--chart-dewpoint').trim() || '#6b8e6b',
  };
}

/**
 * Explicit x-axis tick values at 4-hour intervals across the 24h window,
 * aligned to 4-hour clock boundaries (…, 00:00, 04:00, 08:00, …). Returned as
 * Date[] so Plot renders exactly these and doesn't fall back to its own "nice"
 * 3-hour spacing (d3 has no 4-hour nice interval, so a count hint won't do it).
 */
export function xTimeTickValues(startMs: number, endMs: number): Date[] {
  const FOUR_H = 4 * 3600 * 1000;
  const d = new Date(startMs);
  d.setMinutes(0, 0, 0);
  // Advance to the next clock hour that is a multiple of 4.
  while (d.getHours() % 4 !== 0) d.setHours(d.getHours() + 1);
  const ticks: Date[] = [];
  for (let t = d.getTime(); t <= endMs; t += FOUR_H) ticks.push(new Date(t));
  return ticks;
}

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
  const t = tokens();

  // UI-13: dual-layer rendering. Raw 1-minute points in light grey behind,
  // LOESS-smoothed line (span=0.15) on top. Pitfall 2: marks array order
  // determines z-order, so raw line MUST come before smoothed line.
  const rawYs = safe.map(p => p.rate_per_min);
  const smoothedYs = loess(rawYs, 0.15);
  const smoothed: MuonPoint[] = safe.map((p, i) => ({ ts: p.ts, rate_per_min: smoothedYs[i] }));
  const last = smoothed.length > 0 ? smoothed[smoothed.length - 1] : null;
  const yScale = niceFloorDomain([...rawYs, ...smoothedYs], 4);

  return Plot.plot({
    width,
    height: 240,
    marginLeft: 46,
    marginRight: 12,
    marginBottom: 28,
    marginTop: 8,
    x: { type: 'time', domain: [start, end], ticks: xTimeTickValues(start.getTime(), end.getTime()) },
    y: { label: null, grid: true, ...(yScale ? { domain: yScale.domain, ticks: yScale.ticks } : {}) },
    marks: [
      Plot.gridY({ stroke: t.grid, strokeWidth: 1 }),
      // Raw line — BEHIND smoothed (array order = z-order; Pitfall 2)
      Plot.line(safe, {
        x: (d: MuonPoint) => new Date(d.ts * 1000),
        y: 'rate_per_min',
        stroke: t.raw,
        strokeWidth: 0.5,
        strokeOpacity: 0.55,
      }),
      // Smoothed line — on top
      Plot.line(smoothed, {
        x: (d: MuonPoint) => new Date(d.ts * 1000),
        y: 'rate_per_min',
        stroke: t.data,
        strokeWidth: 2,
        strokeLinejoin: 'round',
        strokeLinecap: 'round',
      }),
      ...(last
        ? [
            Plot.dot([last], {
              x: (d: MuonPoint) => new Date(d.ts * 1000),
              y: 'rate_per_min',
              fill: t.marker,
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
  // niceFloorDomain handles negative winter temps + guarantees the lowest tick
  // sits below the data min, so the line never dips under the lowest gridline.
  const valid = data.filter(p => p.temp_c != null);
  const t = tokens();
  const rawYs = valid.map(p => p.temp_c as number);
  const smoothedYs = loess(rawYs, 0.15);
  const smoothed: WeatherPoint[] = valid.map((p, i) => ({ ts: p.ts, temp_c: smoothedYs[i] }));
  const last = smoothed.length > 0 ? smoothed[smoothed.length - 1] : null;
  const yScale = niceFloorDomain([...rawYs, ...smoothedYs], 3);

  return Plot.plot({
    width,
    height: 180,
    marginLeft: 46,
    marginRight: 12,
    marginBottom: 28,
    marginTop: 8,
    x: { type: 'time', domain: [start, end], ticks: xTimeTickValues(start.getTime(), end.getTime()) },
    y: { label: null, grid: true, ...(yScale ? { domain: yScale.domain, ticks: yScale.ticks } : {}) },
    marks: [
      Plot.gridY({ stroke: t.grid, strokeWidth: 1 }),
      // Raw line — BEHIND smoothed (array order = z-order; Pitfall 2 from 08-RESEARCH)
      Plot.line(valid, {
        x: (d: WeatherPoint) => new Date(d.ts * 1000),
        y: (d: WeatherPoint) => d.temp_c as number,
        stroke: t.raw,
        strokeWidth: 0.5,
        strokeOpacity: 0.55,
      }),
      // Smoothed line — on top
      Plot.line(smoothed, {
        x: (d: WeatherPoint) => new Date(d.ts * 1000),
        y: (d: WeatherPoint) => d.temp_c as number,
        stroke: t.data,
        strokeWidth: 2,
        strokeLinejoin: 'round',
        strokeLinecap: 'round',
      }),
      ...(last
        ? [
            Plot.dot([last], {
              x: (d: WeatherPoint) => new Date(d.ts * 1000),
              y: (d: WeatherPoint) => d.temp_c as number,
              fill: t.marker,
              r: 5,
            }),
          ]
        : []),
    ],
  });
}

export function buildPressurePlot(data: WeatherPoint[], width: number): SVGElement | HTMLElement {
  const now = Date.now();
  const start = new Date(now - WINDOW_SEC * 1000);
  const end = new Date(now);
  const t = tokens();

  const valid = data.filter((p) => p.pressure_hpa != null);
  const rawYs = valid.map((p) => p.pressure_hpa as number);
  const smoothedYs = loess(rawYs, 0.15);
  const smoothed: WeatherPoint[] = valid.map((p, i) => ({ ts: p.ts, pressure_hpa: smoothedYs[i] }));
  const last = smoothed.length > 0 ? smoothed[smoothed.length - 1] : null;
  const yScale = niceFloorDomain([...rawYs, ...smoothedYs], 3);

  return Plot.plot({
    width,
    height: 180,
    marginLeft: 46,
    marginRight: 12,
    marginBottom: 28,
    marginTop: 8,
    x: { type: 'time', domain: [start, end], ticks: xTimeTickValues(start.getTime(), end.getTime()) },
    y: { label: null, grid: true, ...(yScale ? { domain: yScale.domain, ticks: yScale.ticks } : {}) },
    marks: [
      Plot.gridY({ stroke: t.grid, strokeWidth: 1 }),
      Plot.line(valid, {
        x: (d: WeatherPoint) => new Date(d.ts * 1000),
        y: (d: WeatherPoint) => d.pressure_hpa as number,
        stroke: t.raw,
        strokeWidth: 0.5,
        strokeOpacity: 0.55,
      }),
      Plot.line(smoothed, {
        x: (d: WeatherPoint) => new Date(d.ts * 1000),
        y: (d: WeatherPoint) => d.pressure_hpa as number,
        stroke: t.data,
        strokeWidth: 2,
        strokeLinejoin: 'round',
        strokeLinecap: 'round',
      }),
      ...(last
        ? [
            Plot.dot([last], {
              x: (d: WeatherPoint) => new Date(d.ts * 1000),
              y: (d: WeatherPoint) => d.pressure_hpa as number,
              fill: t.marker,
              r: 5,
            }),
          ]
        : []),
    ],
  });
}

interface HumPoint { ts: number; humidity: number; }
interface DewPoint { ts: number; dewpoint: number; }

export function buildHumidityDewpointPlot(data: WeatherPoint[], width: number): SVGElement | HTMLElement {
  const now = Date.now();
  const start = new Date(now - WINDOW_SEC * 1000);
  const end = new Date(now);
  const t = tokens();

  // Filter to points carrying BOTH humidity and temp (needed for dewpoint).
  const valid = data.filter((p) => p.humidity_pct != null && p.temp_c != null);

  // Compute dewpoint per point — exactly one dewPointC call per valid point.
  const enriched = valid.map((p) => ({
    ts: p.ts,
    humidity: p.humidity_pct as number,
    dewpoint: dewPointC(p.temp_c as number, p.humidity_pct as number),
  }));

  const humidityYs = enriched.map((e) => e.humidity);
  const dewpointYs = enriched.map((e) => e.dewpoint);
  const smoothedHumidity = loess(humidityYs, 0.15);
  const smoothedDewpoint = loess(dewpointYs, 0.15);

  const humSmoothed: HumPoint[] = enriched.map((e, i) => ({ ts: e.ts, humidity: smoothedHumidity[i] }));
  const dewSmoothed: DewPoint[] = enriched.map((e, i) => ({ ts: e.ts, dewpoint: smoothedDewpoint[i] }));
  const lastHum = humSmoothed.length > 0 ? humSmoothed[humSmoothed.length - 1] : null;
  const lastDew = dewSmoothed.length > 0 ? dewSmoothed[dewSmoothed.length - 1] : null;

  // Shared Y domain so the two lines sit on one axis (UI-SPEC §HumidityChart).
  const yScale = niceFloorDomain([...humidityYs, ...dewpointYs, ...smoothedHumidity, ...smoothedDewpoint], 4);

  return Plot.plot({
    width,
    height: 180,
    marginLeft: 46,
    marginRight: 12,
    marginBottom: 28,
    marginTop: 8,
    x: { type: 'time', domain: [start, end], ticks: xTimeTickValues(start.getTime(), end.getTime()) },
    y: { label: null, grid: true, ...(yScale ? { domain: yScale.domain, ticks: yScale.ticks } : {}) },
    marks: [
      Plot.gridY({ stroke: t.grid, strokeWidth: 1 }),
      // Humidity smoothed line
      Plot.line(humSmoothed, {
        x: (d: HumPoint) => new Date(d.ts * 1000),
        y: 'humidity',
        stroke: t.data,
        strokeWidth: 2,
      }),
      // Dewpoint smoothed line (sage)
      Plot.line(dewSmoothed, {
        x: (d: DewPoint) => new Date(d.ts * 1000),
        y: 'dewpoint',
        stroke: t.dewpoint,
        strokeWidth: 2,
      }),
      // Two current-value markers
      ...(lastHum
        ? [
            Plot.dot([lastHum], {
              x: (d: HumPoint) => new Date(d.ts * 1000),
              y: 'humidity',
              fill: t.marker,
              r: 5,
            }),
          ]
        : []),
      ...(lastDew
        ? [
            Plot.dot([lastDew], {
              x: (d: DewPoint) => new Date(d.ts * 1000),
              y: 'dewpoint',
              fill: t.dewpoint,
              r: 5,
            }),
          ]
        : []),
    ],
  });
}

interface LightPoint { ts: number; lux: number; }

export function buildLightPlot(data: WeatherPoint[], width: number): SVGElement | HTMLElement {
  const now = Date.now();
  const start = new Date(now - WINDOW_SEC * 1000);
  const end = new Date(now);
  const t = tokens();

  // Filter to points carrying lux; clamp ≤ 0 to 1 (LTR-559 dark reading;
  // log domain cannot include 0). Pattern 5 from 08.5-RESEARCH.
  const valid: LightPoint[] = data
    .filter((p) => p.lux != null)
    .map((p) => ({ ts: p.ts, lux: Math.max(1, p.lux as number) }));

  // LOESS in log10 space, back-transform with Math.pow(10, ...).
  const logYs = valid.map((p) => Math.log10(p.lux));
  const smoothedLogYs = loess(logYs, 0.15);
  const smoothed: LightPoint[] = valid.map((p, i) => ({ ts: p.ts, lux: Math.pow(10, smoothedLogYs[i]) }));
  const last = smoothed.length > 0 ? smoothed[smoothed.length - 1] : null;

  return Plot.plot({
    width,
    height: 180,
    marginLeft: 46,
    marginRight: 12,
    marginBottom: 28,
    marginTop: 8,
    x: { type: 'time', domain: [start, end], ticks: xTimeTickValues(start.getTime(), end.getTime()) },
    y: {
      type: 'log',
      grid: true,
      domain: [1, 10000],
      ticks: [1, 10, 100, 1000, 10000],
      tickFormat: (d: number) => (d >= 1000 ? `${d / 1000}k` : `${d}`),
      label: null,
    },
    marks: [
      Plot.gridY({ stroke: t.grid, strokeWidth: 1 }),
      Plot.line(smoothed, {
        x: (d: LightPoint) => new Date(d.ts * 1000),
        y: 'lux',
        stroke: t.data,
        strokeWidth: 2,
        strokeLinejoin: 'round',
        strokeLinecap: 'round',
      }),
      ...(last
        ? [
            Plot.dot([last], {
              x: (d: LightPoint) => new Date(d.ts * 1000),
              y: 'lux',
              fill: t.marker,
              r: 5,
            }),
          ]
        : []),
    ],
  });
}
