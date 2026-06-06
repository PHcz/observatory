import { describe, it, expect } from 'vitest';
// RED until Wave 3 (plan 11-04) creates this module — import fails by design.
import { aqiBand, uvBand, pollenBand } from '$lib/utils/airQualityBands';

// Locked band→{label, token} collapses from 11-UI-SPEC §Color.
describe('airQualityBands aqiBand()', () => {
  it('maps EU AQI values to the locked label + token collapse', () => {
    expect(aqiBand(10)).toEqual({ label: 'Good', token: '--accent' });
    expect(aqiBand(30)).toEqual({ label: 'Fair', token: '--accent' });
    expect(aqiBand(50)).toEqual({ label: 'Moderate', token: '--warn' });
    expect(aqiBand(70)).toEqual({ label: 'Poor', token: '--warn' });
    expect(aqiBand(90)).toEqual({ label: 'Very poor', token: '--alert' });
    expect(aqiBand(120)).toEqual({ label: 'Extremely poor', token: '--alert' });
  });

  it('boundary: >=80 is Very poor (inclusive-low / exclusive-high)', () => {
    expect(aqiBand(80).label).toBe('Very poor');
  });

  it('token for the Moderate band is --warn', () => {
    expect(aqiBand(50).token).toBe('--warn');
  });
});

describe('airQualityBands uvBand()', () => {
  it('maps WHO UV values to label + token + advice', () => {
    expect(uvBand(1)).toEqual({
      label: 'Low',
      token: '--accent',
      advice: 'No protection needed',
    });
    expect(uvBand(4)).toEqual({
      label: 'Moderate',
      token: '--warn',
      advice: 'Seek shade midday; sunscreen advised',
    });
    expect(uvBand(7)).toEqual({
      label: 'High',
      token: '--warn',
      advice: 'Sun protection advised',
    });
    expect(uvBand(9).label).toBe('Very high');
    expect(uvBand(9).token).toBe('--alert');
    expect(uvBand(11).label).toBe('Extreme');
    expect(uvBand(11).token).toBe('--alert');
  });
});

describe('airQualityBands pollenBand()', () => {
  it('tree/weed types use the high thresholds (alder/birch/olive/mugwort)', () => {
    expect(pollenBand('birch', 5).label).toBe('Low');
    expect(pollenBand('birch', 5).token).toBe('--accent');
    expect(pollenBand('birch', 50).label).toBe('Moderate');
    expect(pollenBand('birch', 50).token).toBe('--warn');
    expect(pollenBand('birch', 150).label).toBe('High');
    expect(pollenBand('birch', 150).token).toBe('--alert');
    expect(pollenBand('birch', 400).label).toBe('Very high');
    expect(pollenBand('birch', 400).token).toBe('--alert');
  });

  it('low-threshold types use the lower thresholds (grass/ragweed)', () => {
    expect(pollenBand('grass', 1).label).toBe('Low');
    expect(pollenBand('grass', 10).label).toBe('Moderate');
    expect(pollenBand('grass', 60).label).toBe('High');
    expect(pollenBand('grass', 200).label).toBe('Very high');
  });
});
