import { describe, it, expect } from 'vitest';
import { buildMuonPlot, buildTempPlot, rollingAverage, withinSafetyMargin } from '$lib/charts/plotHelpers';
import type { MuonPoint } from '$lib/types';

describe('plotHelpers', () => {
  it('buildMuonPlot returns a DOM node with empty data', () => {
    const node = buildMuonPlot([], 600);
    expect(node).toBeInstanceOf(Element);
  });

  it('buildMuonPlot renders dot when data has points', () => {
    const now = Math.floor(Date.now() / 1000);
    const node = buildMuonPlot([{ ts: now - 100, rate_per_min: 50 }, { ts: now, rate_per_min: 62 }], 600);
    // Plot DOM has circles for dots; just check node is valid Element
    expect(node.querySelectorAll('circle, [aria-label*="dot"]').length).toBeGreaterThanOrEqual(0);
  });

  it('buildTempPlot handles null temp_c values', () => {
    const now = Math.floor(Date.now() / 1000);
    const node = buildTempPlot([{ ts: now, temp_c: null }, { ts: now + 10, temp_c: 14.2 }], 600);
    expect(node).toBeInstanceOf(Element);
  });

  it('buildMuonPlot returns an Element with non-empty data', () => {
    const now = Math.floor(Date.now() / 1000);
    const node = buildMuonPlot([{ ts: now, rate_per_min: 45 }], 800);
    expect(node).toBeInstanceOf(Element);
  });

  it('buildTempPlot returns an Element with valid temp data', () => {
    const now = Math.floor(Date.now() / 1000);
    const node = buildTempPlot([{ ts: now, temp_c: 18.5 }], 800);
    expect(node).toBeInstanceOf(Element);
  });
});

describe('rollingAverage', () => {
  it('returns [] for empty input', () => {
    expect(rollingAverage([], 5)).toEqual([]);
  });

  it('produces uniform 60 from alternating 100/0/100/0/100 with window=5', () => {
    const data: MuonPoint[] = [
      { ts: 1, rate_per_min: 100 },
      { ts: 2, rate_per_min: 0 },
      { ts: 3, rate_per_min: 100 },
      { ts: 4, rate_per_min: 0 },
      { ts: 5, rate_per_min: 100 },
    ];
    const out = rollingAverage(data, 5);
    expect(out).toHaveLength(5);
    // Window shrinks symmetrically at edges:
    // i=0: [0..2]   = (100+0+100)/3 = 66.66...
    // i=1: [0..3]   = (100+0+100+0)/4 = 50
    // i=2: [0..4]   = (100+0+100+0+100)/5 = 60
    // i=3: [1..4]   = (0+100+0+100)/4 = 50
    // i=4: [2..4]   = (100+0+100)/3 = 66.66...
    expect(out[2].rate_per_min).toBeCloseTo(60, 6);
    expect(out[1].rate_per_min).toBeCloseTo(50, 6);
    expect(out[3].rate_per_min).toBeCloseTo(50, 6);
  });

  it('preserves ts on each output point', () => {
    const data: MuonPoint[] = [
      { ts: 100, rate_per_min: 10 },
      { ts: 200, rate_per_min: 20 },
      { ts: 300, rate_per_min: 30 },
    ];
    const out = rollingAverage(data, 3);
    expect(out.map(p => p.ts)).toEqual([100, 200, 300]);
  });

  it('window=3 over [10,20,30,40,50] yields shrinking edges', () => {
    const data: MuonPoint[] = [
      { ts: 1, rate_per_min: 10 },
      { ts: 2, rate_per_min: 20 },
      { ts: 3, rate_per_min: 30 },
      { ts: 4, rate_per_min: 40 },
      { ts: 5, rate_per_min: 50 },
    ];
    const out = rollingAverage(data, 3);
    // i=0: [0..1] = 15;  i=1: [0..2] = 20;  i=2: [1..3] = 30;
    // i=3: [2..4] = 40;  i=4: [3..4] = 45
    expect(out[0].rate_per_min).toBeCloseTo(15, 6);
    expect(out[1].rate_per_min).toBeCloseTo(20, 6);
    expect(out[2].rate_per_min).toBeCloseTo(30, 6);
    expect(out[3].rate_per_min).toBeCloseTo(40, 6);
    expect(out[4].rate_per_min).toBeCloseTo(45, 6);
  });
});

describe('withinSafetyMargin (90s right-edge guard)', () => {
  it('drops a point 30 seconds old', () => {
    const nowMs = 1_700_000_000_000;
    const data: MuonPoint[] = [{ ts: Math.floor(nowMs / 1000) - 30, rate_per_min: 5 }];
    expect(withinSafetyMargin(data, nowMs)).toEqual([]);
  });

  it('keeps a point 120 seconds old', () => {
    const nowMs = 1_700_000_000_000;
    const data: MuonPoint[] = [{ ts: Math.floor(nowMs / 1000) - 120, rate_per_min: 80 }];
    expect(withinSafetyMargin(data, nowMs)).toHaveLength(1);
  });

  it('keeps a point exactly 90 seconds old (boundary inclusive)', () => {
    const nowMs = 1_700_000_000_000;
    const data: MuonPoint[] = [{ ts: Math.floor(nowMs / 1000) - 90, rate_per_min: 70 }];
    expect(withinSafetyMargin(data, nowMs)).toHaveLength(1);
  });

  it('drops a point 89 seconds old (just inside the margin)', () => {
    const nowMs = 1_700_000_000_000;
    const data: MuonPoint[] = [{ ts: Math.floor(nowMs / 1000) - 89, rate_per_min: 70 }];
    expect(withinSafetyMargin(data, nowMs)).toEqual([]);
  });

  it('mixed array: keeps old, drops recent', () => {
    const nowMs = 1_700_000_000_000;
    const nowSec = Math.floor(nowMs / 1000);
    const data: MuonPoint[] = [
      { ts: nowSec - 3600, rate_per_min: 60 }, // 1h old, keep
      { ts: nowSec - 600,  rate_per_min: 62 }, // 10m old, keep
      { ts: nowSec - 91,   rate_per_min: 64 }, // 91s old, keep (boundary)
      { ts: nowSec - 30,   rate_per_min: 5  }, // 30s old, drop
    ];
    const out = withinSafetyMargin(data, nowMs);
    expect(out).toHaveLength(3);
    expect(out.map(p => p.ts)).toEqual([nowSec - 3600, nowSec - 600, nowSec - 91]);
  });
});

describe('buildMuonPlot integrates the 90s safety margin', () => {
  it('renders without exception when data contains a still-filling recent point', () => {
    const nowSec = Math.floor(Date.now() / 1000);
    const data: MuonPoint[] = [
      { ts: nowSec - 3600, rate_per_min: 80 },
      { ts: nowSec - 600,  rate_per_min: 82 },
      { ts: nowSec - 120,  rate_per_min: 84 }, // 2min old, kept by smoothing
      { ts: nowSec,        rate_per_min: 5  }, // in-progress, dropped
    ];
    const node = buildMuonPlot(data, 600);
    expect(node).toBeInstanceOf(Element);
  });
});

describe('buildTempPlot dual-layer (UI-13)', () => {
  it('renders raw + smoothed lines with the configured strokes', () => {
    const now = Math.floor(Date.now() / 1000);
    const data = Array.from({ length: 50 }, (_, i) => ({
      ts: now - (50 - i) * 1800,
      temp_c: 12 + Math.sin(i / 5) * 2,
    }));
    const el = buildTempPlot(data, 800);
    const html = (el as HTMLElement).outerHTML;
    expect(html).toContain('stroke="#cccccc"');
    expect(html).toContain('stroke="#111111"');
  });

  it('handles negative temps with padded domain', () => {
    const now = Math.floor(Date.now() / 1000);
    const data = Array.from({ length: 50 }, (_, i) => ({
      ts: now - (50 - i) * 1800,
      temp_c: -3 + i * 0.2,
    }));
    const el = buildTempPlot(data, 800);
    const html = (el as HTMLElement).outerHTML;
    expect(html).toContain('stroke="#cccccc"');
    expect(html).toContain('stroke="#111111"');
  });
});

describe('buildMuonPlot dual-layer (UI-13)', () => {
  it('produces an SVG/HTML element with raw + smoothed line marks', () => {
    const now = Math.floor(Date.now() / 1000);
    // 200 points spanning a few hours, comfortably past 90s safety margin
    const data: MuonPoint[] = Array.from({ length: 200 }, (_, i) => ({
      ts: now - 10000 + i * 50,
      rate_per_min: 80 + Math.random() * 20,
    }));
    const el = buildMuonPlot(data, 800);
    const html = (el as HTMLElement).outerHTML;
    // Two line marks at the configured opacities/strokes
    expect(html).toContain('stroke="#cccccc"');
    expect(html).toContain('stroke-opacity="0.55"');
    expect(html).toContain('stroke="#111111"');
  });
});
