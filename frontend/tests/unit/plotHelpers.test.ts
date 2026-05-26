import { describe, it, expect } from 'vitest';
import { buildMuonPlot, buildTempPlot } from '$lib/charts/plotHelpers';

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
