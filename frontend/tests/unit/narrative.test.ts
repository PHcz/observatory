import { describe, it, expect } from 'vitest';
import { numberToWord, composeSubtitle } from '$lib/utils/narrative';

describe('numberToWord', () => {
  it('returns word for 1', () => expect(numberToWord(1)).toBe('one'));
  it('returns word for 5', () => expect(numberToWord(5)).toBe('five'));
  it('returns word for 12', () => expect(numberToWord(12)).toBe('twelve'));
  it('returns word for 20', () => expect(numberToWord(20)).toBe('twenty'));
  it('returns numeral for 21', () => expect(numberToWord(21)).toBe('21'));
  it('returns numeral for 42', () => expect(numberToWord(42)).toBe('42'));
  it('returns empty string for 0', () => expect(numberToWord(0)).toBe(''));
  it('returns empty string for negative', () => expect(numberToWord(-5)).toBe(''));
  it('returns empty string for non-finite', () => expect(numberToWord(NaN)).toBe(''));
});

describe('composeSubtitle', () => {
  it('includes time-of-day descriptor: morning for hour 8', () => {
    const result = composeSubtitle({ hourLocal: 8, pressureTrendHpaPerHr: null, muonRate: null, ukSmallQuakeCount: 0, ukMaxMag: 0 });
    expect(result).toContain('morning');
  });

  it('includes time-of-day descriptor: afternoon for hour 14', () => {
    const result = composeSubtitle({ hourLocal: 14, pressureTrendHpaPerHr: null, muonRate: null, ukSmallQuakeCount: 0, ukMaxMag: 0 });
    expect(result).toContain('afternoon');
  });

  it('includes time-of-day descriptor: evening for hour 19', () => {
    const result = composeSubtitle({ hourLocal: 19, pressureTrendHpaPerHr: null, muonRate: null, ukSmallQuakeCount: 0, ukMaxMag: 0 });
    expect(result).toContain('evening');
  });

  it('includes time-of-day descriptor: night for hour 23', () => {
    const result = composeSubtitle({ hourLocal: 23, pressureTrendHpaPerHr: null, muonRate: null, ukSmallQuakeCount: 0, ukMaxMag: 0 });
    expect(result).toContain('night');
  });

  it('includes "Pressure rising" when trend > 0.3', () => {
    const result = composeSubtitle({ hourLocal: 8, pressureTrendHpaPerHr: 0.5, muonRate: null, ukSmallQuakeCount: 0, ukMaxMag: 0 });
    expect(result).toContain('Pressure rising');
  });

  it('includes "Pressure falling" when trend < -0.3', () => {
    const result = composeSubtitle({ hourLocal: 8, pressureTrendHpaPerHr: -0.5, muonRate: null, ukSmallQuakeCount: 0, ukMaxMag: 0 });
    expect(result).toContain('Pressure falling');
  });

  it('includes "Pressure steady" when trend is small', () => {
    const result = composeSubtitle({ hourLocal: 8, pressureTrendHpaPerHr: 0.1, muonRate: null, ukSmallQuakeCount: 0, ukMaxMag: 0 });
    expect(result).toContain('Pressure steady');
  });

  it('omits pressure phrase when trend is null', () => {
    const result = composeSubtitle({ hourLocal: 8, pressureTrendHpaPerHr: null, muonRate: null, ukSmallQuakeCount: 0, ukMaxMag: 0 });
    expect(result).not.toContain('Pressure');
  });

  it('includes "twelve muons per minute" for muonRate 12', () => {
    const result = composeSubtitle({ hourLocal: 8, pressureTrendHpaPerHr: null, muonRate: 12, ukSmallQuakeCount: 0, ukMaxMag: 0 });
    expect(result).toContain('twelve muons per minute');
  });

  it('omits muon phrase when muonRate is null', () => {
    const result = composeSubtitle({ hourLocal: 8, pressureTrendHpaPerHr: null, muonRate: null, ukSmallQuakeCount: 0, ukMaxMag: 0 });
    expect(result).not.toContain('muons per minute');
  });

  it('includes "three small earthquakes in Britain this week" for count=3, maxMag=2.8', () => {
    const result = composeSubtitle({ hourLocal: 8, pressureTrendHpaPerHr: null, muonRate: null, ukSmallQuakeCount: 3, ukMaxMag: 2.8 });
    expect(result).toContain('three small earthquakes in Britain this week');
  });

  it('uses "moderate" when maxMag is between 3.0 and 4.0', () => {
    const result = composeSubtitle({ hourLocal: 8, pressureTrendHpaPerHr: null, muonRate: null, ukSmallQuakeCount: 2, ukMaxMag: 3.5 });
    expect(result).toContain('moderate');
  });

  it('omits quake phrase when count is 0', () => {
    const result = composeSubtitle({ hourLocal: 8, pressureTrendHpaPerHr: null, muonRate: null, ukSmallQuakeCount: 0, ukMaxMag: 2.0 });
    expect(result).not.toContain('earthquake');
  });

  it('when all optional fields null, produces descriptor with no null/undefined', () => {
    const result = composeSubtitle({ hourLocal: 6, pressureTrendHpaPerHr: null, muonRate: null, ukSmallQuakeCount: 0, ukMaxMag: 0 });
    expect(result).not.toContain('null');
    expect(result).not.toContain('undefined');
    expect(result).toContain('morning');
    expect(result).toMatch(/\.$/);;
  });

  it('full combination: evening, rising pressure, 12 muons, 3 small quakes', () => {
    const result = composeSubtitle({ hourLocal: 19, pressureTrendHpaPerHr: 0.5, muonRate: 12, ukSmallQuakeCount: 3, ukMaxMag: 2.8 });
    expect(result).toContain('evening');
    expect(result).toContain('Pressure rising');
    expect(result).toContain('twelve muons per minute');
    expect(result).toContain('three small earthquakes in Britain this week');
  });
});
