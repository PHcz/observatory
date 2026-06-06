import { describe, it, expect } from 'vitest';
// RED until Wave 3 (plan 10-04) creates this module — import fails by design.
import { condition } from '$lib/utils/weatherCodes';

// Full WMO 4677 / Open-Meteo code list from 10-RESEARCH §WMO weather_code table.
const WMO_CODES = [
  0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77, 80, 81, 82, 85, 86,
  95, 96, 99,
];

describe('weatherCodes condition()', () => {
  it('every WMO code in the table resolves to a glyph + non-empty label', () => {
    for (const code of WMO_CODES) {
      const c = condition(code);
      expect(typeof c.glyph).toBe('string');
      expect(c.glyph.length).toBeGreaterThan(0);
      expect(typeof c.label).toBe('string');
      expect(c.label.length).toBeGreaterThan(0);
    }
  });

  it('unknown code falls back to cloud + dash label', () => {
    expect(condition(999)).toEqual({ glyph: 'cloud', label: '—' });
  });

  it('null code falls back (does not throw)', () => {
    expect(() => condition(null)).not.toThrow();
    expect(condition(null)).toEqual({ glyph: 'cloud', label: '—' });
  });
});
