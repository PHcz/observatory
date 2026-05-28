import { describe, it, expect } from 'vitest';
import { loess } from '$lib/charts/loess';

describe('loess', () => {
  it('returns empty for empty input', () => {
    expect(loess([], 0.15)).toEqual([]);
  });
  it('returns identity for n<3', () => {
    expect(loess([5], 0.15)).toEqual([5]);
    expect(loess([5, 7], 0.15)).toEqual([5, 7]);
  });
  it('flat series stays flat', () => {
    const out = loess([5, 5, 5, 5, 5], 0.15);
    for (const v of out) expect(v).toBeCloseTo(5, 9);
  });
  it('reduces amplitude of square wave', () => {
    const wave = [0, 10, 0, 10, 0, 10, 0, 10, 0, 10];
    const out = loess(wave, 0.5);
    const amp = Math.max(...out) - Math.min(...out);
    expect(amp).toBeLessThan(10);
  });
});
