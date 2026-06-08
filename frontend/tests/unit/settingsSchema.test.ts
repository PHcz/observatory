import { describe, it, expect } from 'vitest';
import { DEFAULTS, parseSettings, ALL_PANELS } from '$lib/utils/settingsSchema';

describe('settingsSchema DEFAULTS', () => {
  it('theme defaults to auto', () => {
    expect(DEFAULTS.theme).toBe('auto');
  });

  it('most panels default to visible (true); muonDiagnostics + muonGainDrift default OFF', () => {
    // Phase 16 (ENH-01/02): muon diagnostic panels are advanced/verbose — default off.
    // All other panels (including the 3 new weather panels) default on.
    expect(DEFAULTS.panels.muonDiagnostics).toBe(false);
    expect(DEFAULTS.panels.muonGainDrift).toBe(false);
    const onPanels = Object.entries(DEFAULTS.panels).filter(([k]) => k !== 'muonDiagnostics' && k !== 'muonGainDrift');
    expect(onPanels.every(([, v]) => v === true)).toBe(true);
  });

  it('exposes exactly 23 panel keys', () => {
    expect(Object.keys(DEFAULTS.panels).length).toBe(23);
    expect(ALL_PANELS.length).toBe(23);
  });

  it('PanelKey enum has the locked members in locked order', () => {
    // Phase 13 (MU2-05/06/07): adcSpectrum/barometric/nmdbOverlay/forbush after muonChart.
    // Phase 16 (ENH-01/02/04/05): todayStrip/zambrettiCard/weatherAlerts after statsRow;
    //   muonDiagnostics/muonGainDrift after muonChart (before adcSpectrum group).
    const expected = [
      'headerPanel',
      'statsRow',
      'todayStrip',
      'zambrettiCard',
      'weatherAlerts',
      'forecast',
      'airQuality',
      'muonChart',
      'muonDiagnostics',
      'muonGainDrift',
      'adcSpectrum',
      'barometric',
      'nmdbOverlay',
      'forbush',
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
