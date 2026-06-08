import * as Plot from '@observablehq/plot';
import type {
  MuonPoint,
  WeatherPoint,
  AdcHistogramBin,
  BarometricFitResult,
  NmdbSeriesPoint,
  NmdbLocalPoint,
} from '$lib/types';
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
      accent: '#6b8e6b',
      warn: '#c97f3a',
      alert: '#b8504a',
      bg: '#ffffff',
    };
  }
  const cs = getComputedStyle(document.documentElement);
  return {
    raw: cs.getPropertyValue('--chart-raw').trim() || '#cccccc',
    data: cs.getPropertyValue('--chart-data').trim() || '#111111',
    grid: cs.getPropertyValue('--chart-grid').trim() || '#f0f0ec',
    marker: cs.getPropertyValue('--chart-marker').trim() || '#6b8e6b',
    dewpoint: cs.getPropertyValue('--chart-dewpoint').trim() || '#6b8e6b',
    accent: cs.getPropertyValue('--accent').trim() || '#6b8e6b',
    warn: cs.getPropertyValue('--warn').trim() || '#c97f3a',
    alert: cs.getPropertyValue('--alert').trim() || '#b8504a',
    bg: cs.getPropertyValue('--bg').trim() || '#ffffff',
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
 * One tick per local midnight across [startMs, endMs] — for multi-day charts
 * (e.g. the 7-day cosmic-ray overlay) where 4-hourly ticks crowd the axis.
 * DST-safe (steps by calendar day, not a fixed 24h).
 */
export function xDateTickValues(startMs: number, endMs: number): Date[] {
  const d = new Date(startMs);
  d.setHours(0, 0, 0, 0);
  if (d.getTime() < startMs) d.setDate(d.getDate() + 1); // first midnight >= start
  const ticks: Date[] = [];
  for (let t = d.getTime(); t <= endMs; ) {
    ticks.push(new Date(t));
    const next = new Date(t);
    next.setDate(next.getDate() + 1);
    t = next.getTime();
  }
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

  // ENH-02: anomaly dots — bins with anomaly_severity set (|z|>3 warn, |z|>5 alert).
  const warnDots = safe.filter(p => p.anomaly_severity === 'warn');
  const alertDots = safe.filter(p => p.anomaly_severity === 'alert');

  // ENH-02: Poisson band — ±1σ (√N/Δt) per bin, drawn around the SMOOTHED line
  // rather than the raw per-bucket values. Centering on the LOESS line turns it
  // into a clean ribbon (the spec's "±1σ around the LOESS line"); the original
  // raw-centered band was a jagged sliver lost inside the ±60 per-minute scatter.
  // Half-width σ = (upper − lower) / 2 from the server-computed bounds.
  const hasBand = safe.some(p => p.lower_1sigma != null && p.upper_1sigma != null);
  const bandData = hasBand
    ? safe
        .map((p, i) => {
          if (p.lower_1sigma == null || p.upper_1sigma == null) return null;
          const sigma = ((p.upper_1sigma as number) - (p.lower_1sigma as number)) / 2;
          return { ts: p.ts, band_lo: smoothedYs[i] - sigma, band_hi: smoothedYs[i] + sigma };
        })
        .filter((x): x is { ts: number; band_lo: number; band_hi: number } => x !== null)
    : [];

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
      // Layer 1: Raw scatter — BEHIND everything (array order = z-order; Pitfall 2)
      Plot.line(safe, {
        x: (d: MuonPoint) => new Date(d.ts * 1000),
        y: 'rate_per_min',
        stroke: t.raw,
        strokeWidth: 0.5,
        strokeOpacity: 0.55,
      }),
      // Layer 2: Poisson confidence band (ENH-02) — accent ribbon around the LOESS
      // line, on top of the raw scatter so it reads. Guard: only when band fields
      // are present (older cached rows omit them).
      ...(hasBand
        ? [
            Plot.areaY(bandData, {
              x: (d: { ts: number }) => new Date(d.ts * 1000),
              y1: 'band_lo',
              y2: 'band_hi',
              fill: t.marker,
              fillOpacity: 0.18,
              stroke: 'none',
            }),
          ]
        : []),
      // Layer 3: Smoothed LOESS line — on top of raw + band
      Plot.line(smoothed, {
        x: (d: MuonPoint) => new Date(d.ts * 1000),
        y: 'rate_per_min',
        stroke: t.data,
        strokeWidth: 2,
        strokeLinejoin: 'round',
        strokeLinecap: 'round',
      }),
      // Layer 4a: |z|>3 anomaly dots (warn colour) — above LOESS line
      ...(warnDots.length > 0
        ? [
            Plot.dot(warnDots, {
              x: (d: MuonPoint) => new Date(d.ts * 1000),
              y: 'rate_per_min',
              r: 4,
              fill: t.warn,
              stroke: t.bg,
              strokeWidth: 1.5,
            }),
          ]
        : []),
      // Layer 4b: |z|>5 anomaly dots (alert colour) — above warn dots
      ...(alertDots.length > 0
        ? [
            Plot.dot(alertDots, {
              x: (d: MuonPoint) => new Date(d.ts * 1000),
              y: 'rate_per_min',
              r: 4,
              fill: t.alert,
              stroke: t.bg,
              strokeWidth: 1.5,
            }),
          ]
        : []),
      // Layer 5: current-value marker
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
      // Layer 6: sea-level reference was removed (ENH-01 — see 16-05-SUMMARY).
      // The y-axis is raw events/min (~140-260) so a rule at y=1.0 is unit-mismatched
      // and invisible. Replaced with a stat annotation in MuonChart.svelte.
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

// ---------------------------------------------------------------------------
// Phase 13 (MU2-05/06) — live muon science build functions.
// Tokens read at render time (theme-swap safe); no hex literals introduced.
// ---------------------------------------------------------------------------

const NMDB_WINDOW_SEC = 7 * 86400;

/**
 * ADC pulse-height histogram (bar chart, 20-unit bins). The modal bin (the
 * MIP / Landau peak) is highlighted in --accent; all other bars are neutral
 * --chart-raw. x label is the hyphen-minus form "ADC (0-1023)" (RUF lesson).
 */
export function buildAdcHistogramPlot(
  hist: AdcHistogramBin[],
  width: number,
): SVGElement | HTMLElement {
  const t = tokens();

  // Modal bin index — the bar with the highest count gets the sage highlight.
  let modalIdx = -1;
  let modalCount = -Infinity;
  for (let i = 0; i < hist.length; i++) {
    if (hist[i].count > modalCount) {
      modalCount = hist[i].count;
      modalIdx = i;
    }
  }
  const modal = modalIdx >= 0 ? hist[modalIdx] : null;

  return Plot.plot({
    width,
    height: 180,
    marginLeft: 46,
    marginRight: 12,
    marginBottom: 28,
    // Headroom for the "MIP peak" label, which sits above the tallest (modal)
    // bar. With the old 8px top margin the 11px label + dy overflowed the SVG
    // top and was clipped (only the bottoms of the glyphs showed over the bar).
    marginTop: 24,
    x: { label: 'ADC (0-1023)', tickFormat: (d: number) => `${d}` },
    y: { label: null, grid: true },
    marks: [
      Plot.gridY({ stroke: t.grid, strokeWidth: 1 }),
      Plot.rectY(hist, {
        x: 'bin_center',
        y: 'count',
        interval: 20,
        fill: (d: AdcHistogramBin) =>
          modal != null && d.bin_center === modal.bin_center ? t.accent : t.raw,
      }),
      ...(modal != null
        ? [
            Plot.text([modal], {
              x: 'bin_center',
              y: 'count',
              text: () => 'MIP peak',
              dy: -8,
              lineAnchor: 'bottom',
              fill: t.accent,
              fontSize: 11,
            }),
          ]
        : []),
    ],
  });
}

/**
 * Barometric coefficient scatter: raw rate-vs-pressure points (--chart-raw)
 * with the fitted regression line (--accent) overlaid. The fit line is drawn
 * across the observed pressure range using the fitted slope (β in %/hPa).
 */
export function buildBarometricScatterPlot(
  points: { pressure_hpa: number; rate_per_min: number }[],
  fit: BarometricFitResult | null,
  width: number,
): SVGElement | HTMLElement {
  const t = tokens();

  // Fit line endpoints: a straight segment across the observed pressure range.
  // β is the % change in rate per hPa; convert to an absolute slope around the
  // mean pressure/rate so the line sits visually over the scatter.
  const fitLine: { pressure_hpa: number; rate_per_min: number }[] = [];
  if (fit != null && points.length > 0) {
    const pressures = points.map((p) => p.pressure_hpa);
    const rates = points.map((p) => p.rate_per_min);
    const pMin = Math.min(...pressures);
    const pMax = Math.max(...pressures);
    const pMean = pressures.reduce((a, b) => a + b, 0) / pressures.length;
    const rMean = rates.reduce((a, b) => a + b, 0) / rates.length;
    // slope per hPa in absolute rate units = (β/100) * rMean.
    const slope = (fit.beta / 100) * rMean;
    fitLine.push(
      { pressure_hpa: pMin, rate_per_min: rMean + slope * (pMin - pMean) },
      { pressure_hpa: pMax, rate_per_min: rMean + slope * (pMax - pMean) },
    );
  }

  return Plot.plot({
    width,
    height: 180,
    marginLeft: 46,
    marginRight: 12,
    marginBottom: 28,
    marginTop: 8,
    x: { label: 'pressure (hPa)' },
    y: { label: 'rate / min', grid: true },
    marks: [
      Plot.gridY({ stroke: t.grid, strokeWidth: 1 }),
      Plot.dot(points, {
        x: 'pressure_hpa',
        y: 'rate_per_min',
        fill: t.raw,
        r: 3,
      }),
      ...(fitLine.length > 0
        ? [
            Plot.line(fitLine, {
              x: 'pressure_hpa',
              y: 'rate_per_min',
              stroke: t.accent,
              strokeWidth: 2,
            }),
          ]
        : []),
    ],
  });
}

/**
 * NMDB-vs-local %-of-baseline overlay over a shared 7-day time axis. The local
 * muon flux uses the primary --chart-data emphasis (with a current-value
 * --chart-marker dot); the Oulu neutron monitor uses muted --chart-raw. A 100%
 * reference rule (--chart-grid) marks the shared baseline so a Forbush dip
 * lines up across both despite very different absolute count rates.
 */
export function buildOverlayPlot(
  local: Pick<NmdbLocalPoint, 'ts' | 'pct_baseline'>[],
  nmdb: Pick<NmdbSeriesPoint, 'ts' | 'pct_baseline'>[],
  width: number,
): SVGElement | HTMLElement {
  const now = Date.now();
  const start = new Date(now - NMDB_WINDOW_SEC * 1000);
  const end = new Date(now);
  const t = tokens();

  const localValid = local.filter((p) => p.pct_baseline != null);
  const nmdbValid = nmdb.filter((p) => p.pct_baseline != null);
  const lastLocal = localValid.length > 0 ? localValid[localValid.length - 1] : null;

  return Plot.plot({
    width,
    height: 240,
    marginLeft: 46,
    marginRight: 12,
    marginBottom: 28,
    marginTop: 8,
    x: {
      type: 'time',
      domain: [start, end],
      // Dates only — one tick per day; 4-hourly ticks crowd a 7-day axis.
      ticks: xDateTickValues(start.getTime(), end.getTime()),
      tickFormat: (d: Date) => d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
    },
    y: { label: '% of baseline', grid: true },
    marks: [
      Plot.gridY({ stroke: t.grid, strokeWidth: 1 }),
      // 100% baseline reference rule.
      Plot.ruleY([100], { stroke: t.grid, strokeWidth: 1 }),
      // NMDB (Oulu) reference line — muted.
      Plot.line(nmdbValid, {
        x: (d: Pick<NmdbSeriesPoint, 'ts' | 'pct_baseline'>) => new Date(d.ts * 1000),
        y: (d: Pick<NmdbSeriesPoint, 'ts' | 'pct_baseline'>) => d.pct_baseline as number,
        stroke: t.raw,
        strokeWidth: 2,
      }),
      // Local muon flux line — primary emphasis.
      Plot.line(localValid, {
        x: (d: Pick<NmdbLocalPoint, 'ts' | 'pct_baseline'>) => new Date(d.ts * 1000),
        y: (d: Pick<NmdbLocalPoint, 'ts' | 'pct_baseline'>) => d.pct_baseline as number,
        stroke: t.data,
        strokeWidth: 2,
      }),
      ...(lastLocal != null
        ? [
            Plot.dot([lastLocal], {
              x: (d: Pick<NmdbLocalPoint, 'ts' | 'pct_baseline'>) => new Date(d.ts * 1000),
              y: (d: Pick<NmdbLocalPoint, 'ts' | 'pct_baseline'>) => d.pct_baseline as number,
              fill: t.marker,
              r: 5,
            }),
          ]
        : []),
    ],
  });
}
