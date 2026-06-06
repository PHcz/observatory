import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
// RED until Wave 3 (plan 11-04): the panel + airQuality store do not exist yet.
import AirQualityPanel from '$lib/panels/AirQualityPanel.svelte';
import { setAirQuality } from '$lib/stores/airQuality';
import { settingsStore } from '$lib/stores/settings';

// Seed shape mirrors the /api/air-quality contract (OAQ-02 + UI-SPEC).
function snapshot(overrides: Record<string, unknown> = {}) {
  return {
    aqi: 70,
    pollutants: {
      pm2_5: 3.7,
      pm10: 11.2,
      nitrogen_dioxide: 6.1,
      ozone: 68.0,
      sulphur_dioxide: 0.4,
    },
    pollen: {
      alder_pollen: 0,
      birch_pollen: 0,
      grass_pollen: 6.7,
      mugwort_pollen: 0,
      olive_pollen: 0,
      ragweed_pollen: 0,
    },
    uv: 5.5,
    fetched_at: 1_700_000_000,
    ...overrides,
  };
}

beforeEach(() => {
  settingsStore.resetToDefaults();
});

describe('AirQualityPanel', () => {
  it('shows empty state when store has no data', async () => {
    render(AirQualityPanel);
    setAirQuality(null);
    await tick();
    expect(screen.getByText(/Air quality not available yet/i)).toBeTruthy();
  });

  it('renders the AQI hero number + band label and the 5 pollutant cells', async () => {
    render(AirQualityPanel);
    setAirQuality(snapshot({ aqi: 70 }));
    await tick();
    expect(screen.getByText('70')).toBeTruthy();
    expect(screen.getByText(/Poor/i)).toBeTruthy();
    expect(screen.getByText('PM2.5')).toBeTruthy();
    expect(screen.getByText('PM10')).toBeTruthy();
    expect(screen.getByText('NO₂')).toBeTruthy();
    expect(screen.getByText('O₃')).toBeTruthy();
    expect(screen.getByText('SO₂')).toBeTruthy();
  });

  it('renders a UV line with the band advice', async () => {
    render(AirQualityPanel);
    setAirQuality(snapshot({ uv: 5.5 }));
    await tick();
    expect(screen.getByText(/UV/)).toBeTruthy();
    expect(screen.getByText(/Sun protection advised/i)).toBeTruthy();
  });

  it('renders an em dash for a null pollutant without throwing', async () => {
    render(AirQualityPanel);
    setAirQuality(snapshot({ pollutants: { pm2_5: null, pm10: 11.2, nitrogen_dioxide: 6.1, ozone: 68.0, sulphur_dioxide: 0.4 } }));
    await tick();
    expect(screen.getByText('—')).toBeTruthy();
  });

  it('omits the POLLEN caption when all pollen values are null/absent', async () => {
    render(AirQualityPanel);
    setAirQuality(
      snapshot({
        pollen: {
          alder_pollen: null,
          birch_pollen: null,
          grass_pollen: null,
          mugwort_pollen: null,
          olive_pollen: null,
          ragweed_pollen: null,
        },
      }),
    );
    await tick();
    expect(screen.queryByText('POLLEN')).toBeNull();
  });
});
