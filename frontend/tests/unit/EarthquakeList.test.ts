import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import EarthquakeList from '$lib/panels/EarthquakeList.svelte';
import { setEarthquakes, earthquakeStore } from '$lib/stores/earthquakes';

describe('EarthquakeList', () => {
  it('shows empty message when earthquake list is empty', async () => {
    setEarthquakes([]);
    render(EarthquakeList);
    await tick();
    expect(screen.getByText('No earthquakes on record yet.')).toBeTruthy();
  });

  it('renders magnitude pill and source badge for each earthquake', async () => {
    setEarthquakes([
      { ts: 1748275200, source: 'usgs', magnitude: 6.5, place: 'Chile', depth_km: 10 },
      { ts: 1748275100, source: 'emsc', magnitude: 3.2, place: 'UK', depth_km: 5 },
    ]);
    render(EarthquakeList);
    await tick();
    // Big magnitude pill for 6.5
    const bigPills = document.querySelectorAll('.mag-big');
    expect(bigPills.length).toBeGreaterThanOrEqual(1);
    // USGS badge
    expect(screen.getByText('USGS')).toBeTruthy();
  });
});
