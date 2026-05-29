import { describe, it, expect } from 'vitest';
import { dewPointC, dewComfort } from '$lib/utils/dewpoint';

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

describe('dewComfort', () => {
  it('returns "dry, comfortable" below 15°C (incl. the 10.4°C live case)', () => {
    expect(dewComfort(10.4)).toBe('dry, comfortable');
    expect(dewComfort(5)).toBe('dry, comfortable');
    expect(dewComfort(14.9)).toBe('dry, comfortable');
  });

  it('returns "starting to feel sticky" between 15 and 20°C', () => {
    expect(dewComfort(15)).toBe('starting to feel sticky');
    expect(dewComfort(18)).toBe('starting to feel sticky');
    expect(dewComfort(19.9)).toBe('starting to feel sticky');
  });

  it('returns "muggy, oppressive" at 20°C and above', () => {
    expect(dewComfort(20)).toBe('muggy, oppressive');
    expect(dewComfort(24)).toBe('muggy, oppressive');
  });

  it('returns null for NaN / non-finite', () => {
    expect(dewComfort(NaN)).toBe(null);
    expect(dewComfort(Infinity)).toBe(null);
  });
});
