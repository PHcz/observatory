import { describe, it, expect } from 'vitest';
import { illuminatedFraction, isWaxing, moonShadowPath } from '$lib/utils/moonGeometry';

describe('illuminatedFraction', () => {
  it('is 0 at new moon', () => {
    expect(illuminatedFraction(0)).toBeCloseTo(0, 6);
  });
  it('is 1 at full moon', () => {
    expect(illuminatedFraction(0.5)).toBeCloseTo(1, 6);
  });
  it('is 0.5 at both quarters', () => {
    expect(illuminatedFraction(0.25)).toBeCloseTo(0.5, 6);
    expect(illuminatedFraction(0.75)).toBeCloseTo(0.5, 6);
  });
  it('normalises out-of-range phases', () => {
    expect(illuminatedFraction(1)).toBeCloseTo(0, 6);
    expect(illuminatedFraction(-0.5)).toBeCloseTo(1, 6);
  });
});

describe('isWaxing', () => {
  it('is true on the first half of the cycle', () => {
    expect(isWaxing(0.1)).toBe(true);
    expect(isWaxing(0.25)).toBe(true);
    expect(isWaxing(0.49)).toBe(true);
  });
  it('is false on the second half', () => {
    expect(isWaxing(0.5)).toBe(false);
    expect(isWaxing(0.75)).toBe(false);
    expect(isWaxing(0.99)).toBe(false);
  });
});

describe('moonShadowPath', () => {
  const R = 32;

  it('produces a closed two-arc path', () => {
    const d = moonShadowPath(0.3, R);
    expect(d.startsWith('M ')).toBe(true);
    expect(d.trim().endsWith('Z')).toBe(true);
    expect((d.match(/A /g) ?? []).length).toBe(2);
  });

  it('joins the two poles (top and bottom of the disc)', () => {
    // cx=cy=R=32 → top (32,0), bottom (32,64)
    const d = moonShadowPath(0.3, R);
    expect(d).toContain('M 32 0');
    expect(d).toContain('32 64'); // limb arc endpoint = bottom pole
  });

  it('collapses the terminator to a straight diameter (rx=0) at the quarters', () => {
    // At a quarter k=0.5 → rx = R·|1−2·0.5| = 0; the terminator arc has rx 0.
    expect(moonShadowPath(0.25, R)).toContain('A 0 32');
    expect(moonShadowPath(0.75, R)).toContain('A 0 32');
  });

  it('shadows the whole disc at new moon (both arcs full radius)', () => {
    // new moon: rx = R, terminator becomes the opposite semicircle → full disc.
    const d = moonShadowPath(0, R);
    expect(d).toBe('M 32 0 A 32 32 0 0 0 32 64 A 32 32 0 0 0 32 0 Z');
  });

  it('orients the dark limb left when waxing, right when waning', () => {
    // Waxing crescent (lit right → dark-left limb sweep 0).
    expect(moonShadowPath(0.15, R)).toMatch(/M 32 0 A 32 32 0 0 0 32 64/);
    // Waning crescent (lit left → dark-right limb sweep 1).
    expect(moonShadowPath(0.85, R)).toMatch(/M 32 0 A 32 32 0 0 1 32 64/);
  });
});
