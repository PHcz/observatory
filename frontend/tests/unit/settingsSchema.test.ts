import { describe, it, expect } from 'vitest';
import { DEFAULTS, parseSettings, ALL_PANELS } from '$lib/utils/settingsSchema';

describe('settingsSchema DEFAULTS', () => {
  it('theme defaults to auto', () => {
    expect(DEFAULTS.theme).toBe('auto');
  });

  it('all panels default to visible (true)', () => {
    expect(Object.values(DEFAULTS.panels).every((v) => v === true)).toBe(true);
  });

  it('exposes exactly 13 panel keys', () => {
    expect(Object.keys(DEFAULTS.panels).length).toBe(13);
    expect(ALL_PANELS.length).toBe(13);
  });

  it('PanelKey enum has the locked members', () => {
    const expected = [
      'headerPanel',
      'statsRow',
      'forecast',
      'muonChart',
      'spaceWeather',
      'earthquakes',
      'lightning',
      'aurora',
      'temperatureChart',
      'pressureChart',
      'humidityChart',
      'lightChart',
      'healthRow',
    ];
    expect(ALL_PANELS).toEqual(expected);
  });
});

describe('parseSettings', () => {
  it('returns DEFAULTS for null input', () => {
    expect(parseSettings(null)).toEqual(DEFAULTS);
  });

  it('returns DEFAULTS for invalid JSON', () => {
    expect(parseSettings('not json')).toEqual(DEFAULTS);
  });

  it('safe-merges missing panel keys to true', () => {
    const result = parseSettings('{"theme":"dark","panels":{"headerPanel":false}}');
    expect(result.theme).toBe('dark');
    expect(result.panels.headerPanel).toBe(false);
    expect(result.panels.statsRow).toBe(true);
    expect(result.panels.muonChart).toBe(true);
    expect(result.panels.healthRow).toBe(true);
  });

  it('falls back to default theme when theme is invalid', () => {
    const result = parseSettings('{"theme":"bogus"}');
    expect(result.theme).toBe('auto');
  });

  it('returns DEFAULTS-equivalent when panels is absent', () => {
    const result = parseSettings('{"theme":"light"}');
    expect(result.theme).toBe('light');
    expect(result.panels).toEqual(DEFAULTS.panels);
  });
});
