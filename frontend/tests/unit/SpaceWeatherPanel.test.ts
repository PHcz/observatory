import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import SpaceWeatherPanel from '$lib/panels/SpaceWeatherPanel.svelte';

describe('SpaceWeatherPanel', () => {
  it('does not show Forbush copy when kp_index=4', () => {
    render(SpaceWeatherPanel, { props: { kp_index: 4 } });
    expect(screen.queryByText(/Geomagnetic disturbance/)).toBeNull();
  });
  it('shows Geomagnetic disturbance text when kp_index=5', () => {
    render(SpaceWeatherPanel, { props: { kp_index: 5 } });
    expect(screen.getByText(/Geomagnetic disturbance/)).toBeTruthy();
  });
});
