import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
// RED until Wave 3 (plan 10-04): the panel + forecast store do not exist yet.
import ForecastPanel from '$lib/panels/ForecastPanel.svelte';
import { setForecast } from '$lib/stores/forecast';
import { settingsStore } from '$lib/stores/settings';

// Seed shapes mirror the /api/forecast contract (10-RESEARCH Pattern 2 + UI-SPEC).
const HOURLY = [
  { ts: 1_700_000_000, temp_c: 18, precip_prob_pct: 10, weather_code: 0 },
  { ts: 1_700_003_600, temp_c: 17, precip_prob_pct: 20, weather_code: 3 },
];
const DAILY = [
  { ts: 1_700_000_000, temp_max_c: 18, temp_min_c: 10, precip_prob_max_pct: 30, weather_code: 61 },
];

beforeEach(() => {
  settingsStore.resetToDefaults();
});

describe('ForecastPanel', () => {
  it('renders the Local forecast title and OPEN-METEO source when panel visible', async () => {
    settingsStore.update((s) => ({ ...s, panels: { ...s.panels, forecast: true } }));
    render(ForecastPanel);
    setForecast({ hourly: HOURLY, daily: DAILY, vs_actual: null, fetched_at: 1_700_000_000 });
    await tick();
    expect(screen.getByText(/Local forecast/i)).toBeTruthy();
    expect(screen.getByText(/OPEN-METEO/i)).toBeTruthy();
  });

  it('shows empty state when forecast store has no rows', async () => {
    render(ForecastPanel);
    setForecast({ hourly: [], daily: [], vs_actual: null, fetched_at: null });
    await tick();
    expect(screen.getByText(/Forecast not available yet/i)).toBeTruthy();
  });

  it('renders labeled vs-actual lines (labels, verdicts, no em dash, no precip)', async () => {
    render(ForecastPanel);
    setForecast({
      hourly: HOURLY,
      daily: DAILY,
      vs_actual: {
        temp: {
          high: { forecast: 18, actual: 22, delta: 4, label: 'warm', warn: true },
          low: { forecast: 11, actual: 12, delta: 1, label: 'on_track' },
          actual: 22,
        },
        humidity: { forecast: 83, actual: 70 },
        pressure: { forecast: 1004.2, actual: 1007.4 },
        precip: { prob_max: 100 },
      },
      fetched_at: 1_700_000_000,
    });
    await tick();
    // Per-line labels
    expect(screen.getByText('High')).toBeTruthy();
    expect(screen.getByText('Pressure')).toBeTruthy();
    // Verdicts on every line, no em dash; temp + humidity + pressure all compared
    expect(screen.getByText(/forecast 18° \/ actual 22° \(4° warmer\)/i)).toBeTruthy();
    expect(screen.getByText(/forecast 11° \/ actual 12° \(on track\)/i)).toBeTruthy();
    expect(screen.getByText(/forecast 83% \/ actual 70% \(13% lower\)/i)).toBeTruthy();
    expect(
      screen.getByText(/forecast 1004\.2 hPa \/ actual 1007\.4 hPa \(3\.2 hPa higher\)/i),
    ).toBeTruthy();
    // Precipitation line removed from vs-actual (not a comparison)
    expect(screen.queryByText(/chance of precipitation/i)).toBeNull();
  });
});
