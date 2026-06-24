import { describe, it, expect } from 'vitest';
import { paddedYDomain, niceFloorDomain } from '$lib/charts/domain';

describe('paddedYDomain', () => {
  it('returns null for empty array', () => {
    expect(paddedYDomain([])).toBeNull();
  });
  it('pads positive range by 5%', () => {
    expect(paddedYDomain([0, 10])).toEqual([-1, 11]);
  });
  it('preserves negative range', () => {
    expect(paddedYDomain([-5, 5])).toEqual([-6, 6]);
  });
  it('handles flat series via range guard', () => {
    expect(paddedYDomain([7, 7, 7])).toEqual([6, 8]);
  });
});

describe('niceFloorDomain', () => {
  it('returns null for empty array', () => {
    expect(niceFloorDomain([])).toBeNull();
  });

  it('guarantees the lowest tick is strictly BELOW the data minimum (temperature case)', () => {
    // temp dipped to ~13; before the fix the lowest tick was 15 → line below it
    const r = niceFloorDomain([13.2, 18, 24.1], 3)!;
    expect(r.ticks[0]).toBeLessThan(13.2);
    expect(r.domain[0]).toBeLessThanOrEqual(r.ticks[0]);
    expect(r.domain[1]).toBeGreaterThanOrEqual(24.1);
  });

  it('covers a wide multi-series range without burying the low line (humidity+dewpoint case)', () => {
    // humidity 35..78 + dewpoint ~12 on one axis; lowest tick must sit below 12
    const r = niceFloorDomain([12, 13, 35, 60, 78], 4)!;
    expect(r.ticks[0]).toBeLessThan(12);
    expect(r.domain[1]).toBeGreaterThanOrEqual(78);
    // ticks ascending + evenly spaced
    for (let i = 1; i < r.ticks.length; i++) {
      expect(r.ticks[i]).toBeGreaterThan(r.ticks[i - 1]);
    }
  });

  it('drops a step when the data minimum sits exactly on a tick boundary', () => {
    // min 15 on a step-5 grid must NOT be the lowest tick — drop to 10
    const r = niceFloorDomain([15, 25], 2)!;
    expect(r.ticks[0]).toBeLessThan(15);
  });

  it('guarantees the highest tick is strictly ABOVE the data maximum', () => {
    // overlay spike to ~107 must not touch the top tick (105 before the fix)
    const r = niceFloorDomain([78, 95, 107], 5)!;
    expect(r.ticks[r.ticks.length - 1]).toBeGreaterThan(107);
    expect(r.domain[1]).toBeGreaterThan(107);
  });

  it('drops in an extra top tick when the data maximum sits on a boundary', () => {
    // max 25 on a step-5 grid must NOT be the highest tick — bump to 30
    const r = niceFloorDomain([10, 25], 3)!;
    expect(r.ticks[r.ticks.length - 1]).toBeGreaterThan(25);
  });

  it('handles negative values (winter temps)', () => {
    const r = niceFloorDomain([-3, 0, 7], 3)!;
    expect(r.ticks[0]).toBeLessThan(-3);
    expect(r.domain[1]).toBeGreaterThanOrEqual(7);
  });

  it('handles a flat series without NaN/Infinity', () => {
    const r = niceFloorDomain([7, 7, 7], 4)!;
    expect(r.ticks[0]).toBeLessThan(7);
    expect(Number.isFinite(r.domain[0])).toBe(true);
    expect(Number.isFinite(r.domain[1])).toBe(true);
    expect(r.ticks.every(Number.isFinite)).toBe(true);
  });

  it('produces clean (FP-noise-free) tick values', () => {
    const r = niceFloorDomain([1016.1, 1016.4, 1017.3], 3)!;
    // no 1015.0000001 artifacts
    for (const tk of r.ticks) {
      expect(tk).toBe(Number(tk.toFixed(6)));
    }
  });
});
