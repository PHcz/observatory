import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import SpaceWeatherPanel from '#lib/panels/SpaceWeatherPanel.svelte';
import { setSpaceWeather } from '#lib/stores/spaceWeather.js';

describe('SpaceWeatherPanel', () => {
  it('does not show Forbush copy when kp_index=4', async () => {
    render(SpaceWeatherPanel);
    setSpaceWeather({ ts: 1748275200, kp_index: 4, solar_wind_kms: 400, flare_class: null, flare_peak_ts: null });
    await tick();
    expect(screen.queryByText(/Geomagnetic disturbance/)).toBeNull();
  });

  it('shows Geomagnetic disturbance text when kp_index=5', async () => {
    render(SpaceWeatherPanel);
    setSpaceWeather({ ts: 1748275200, kp_index: 5, solar_wind_kms: 400, flare_class: null, flare_peak_ts: null });
    await tick();
    expect(screen.getByText(/Geomagnetic disturbance/)).toBeTruthy();
  });
});

describe('SpaceWeatherPanel — NOAA additions (2026-10)', () => {
  const base = { ts: 1748275200, kp_index: 2, solar_wind_kms: 400, flare_class: null, flare_peak_ts: null };

  it('shows southward IMF Bz with a sign and an aurora hint', async () => {
    render(SpaceWeatherPanel);
    setSpaceWeather({ ...base, imf_bz_nt: -8.1, imf_bt_nt: 12 });
    await tick();
    expect(screen.getByText('−8.1 nT')).toBeTruthy();
    expect(screen.getByText(/southward · favours aurora/)).toBeTruthy();
  });

  it('labels northward Bz as quiet', async () => {
    render(SpaceWeatherPanel);
    setSpaceWeather({ ...base, imf_bz_nt: 3.2, imf_bt_nt: 5 });
    await tick();
    expect(screen.getByText('+3.2 nT')).toBeTruthy();
    expect(screen.getByText(/northward/)).toBeTruthy();
  });

  it('shows solar wind density alongside speed', async () => {
    render(SpaceWeatherPanel);
    setSpaceWeather({ ...base, solar_wind_density: 6.0 });
    await tick();
    expect(screen.getByText(/6\.0 p\/cm³/)).toBeTruthy();
  });

  it('flags a proton flux at the S1 threshold', async () => {
    render(SpaceWeatherPanel);
    setSpaceWeather({ ...base, proton_flux_10mev: 12.5 });
    await tick();
    expect(screen.getByText('12.5 pfu')).toBeTruthy();
    expect(screen.getByText(/radiation storm/)).toBeTruthy();
  });

  it('shows the current NOAA R/S/G scales', async () => {
    render(SpaceWeatherPanel);
    setSpaceWeather({ ...base, noaa_scale_r: 1, noaa_scale_s: 0, noaa_scale_g: 2 });
    await tick();
    expect(screen.getByText('R1 · S0 · G2')).toBeTruthy();
    expect(screen.getByText(/G2 geomagnetic storm/)).toBeTruthy();
  });

  it('renders dashes when the new fields are missing (pre-migration rows)', async () => {
    render(SpaceWeatherPanel);
    setSpaceWeather(base);
    await tick();
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(3);
  });
});
