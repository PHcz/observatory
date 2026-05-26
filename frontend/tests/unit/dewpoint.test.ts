import { describe, it, expect } from 'vitest';
import { dewPointC } from '$lib/utils/dewpoint';

describe('dewPointC', () => {
  it('computes ~9.3 for 20C/50%', () => {
    expect(dewPointC(20, 50)).toBeCloseTo(9.3, 1);
  });

  it('returns NaN for invalid inputs', () => {
    expect(Number.isNaN(dewPointC(NaN, 50))).toBe(true);
  });

  it('returns NaN for zero humidity', () => {
    expect(Number.isNaN(dewPointC(20, 0))).toBe(true);
  });

  it('returns NaN for non-finite humidity', () => {
    expect(Number.isNaN(dewPointC(20, Infinity))).toBe(true);
  });

  it('computes reasonable value at 0C/100%', () => {
    // At 0C/100% humidity, dew point should be ~0C
    expect(dewPointC(0, 100)).toBeCloseTo(0, 0);
  });
});
