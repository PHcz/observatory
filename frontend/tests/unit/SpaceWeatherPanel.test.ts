import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import SpaceWeatherPanel from '$lib/panels/SpaceWeatherPanel.svelte';
import { setSpaceWeather } from '$lib/stores/spaceWeather';

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
