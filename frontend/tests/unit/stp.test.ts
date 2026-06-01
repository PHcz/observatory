import { describe, it, expect } from 'vitest';
import { stpFactor, stpCorrectedRate, REFERENCE_PRESSURE_HPA } from '$lib/utils/stp';

describe('stpCorrectedRate (UKRAA STP method)', () => {
  it('is a no-op at reference conditions (20°C, 1013.25 hPa)', () => {
    expect(stpFactor(20, REFERENCE_PRESSURE_HPA)).toBeCloseTo(1, 9);
    expect(stpCorrectedRate(100, 20, REFERENCE_PRESSURE_HPA)).toBeCloseTo(100, 6);
  });

  it('scales rate down at low pressure (factor > 1)', () => {
    const f = stpFactor(20, 990);
    expect(f).toBeGreaterThan(1);
    expect(stpCorrectedRate(100, 20, 990)).toBeCloseTo(100 / f, 6);
    expect(stpCorrectedRate(100, 20, 990)!).toBeLessThan(100);
  });

  it('scales rate up at high pressure (factor < 1)', () => {
    expect(stpCorrectedRate(100, 20, 1030)!).toBeGreaterThan(100);
  });

  it('returns raw rate when temp or pressure missing/invalid', () => {
    expect(stpCorrectedRate(100, null, 1013.25)).toBe(100);
    expect(stpCorrectedRate(100, 20, null)).toBe(100);
    expect(stpCorrectedRate(100, 20, undefined)).toBe(100);
    expect(stpCorrectedRate(100, 20, 0)).toBe(100);
    expect(stpCorrectedRate(100, 20, -5)).toBe(100);
  });

  it('passes null rate through', () => {
    expect(stpCorrectedRate(null, 20, 1013.25)).toBeNull();
  });
});
