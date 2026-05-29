import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import EarthquakeList from '$lib/panels/EarthquakeList.svelte';
import { setEarthquakes, earthquakeStore } from '$lib/stores/earthquakes';
import type { EarthquakeItem } from '$lib/types';

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

describe('EarthquakeList UI-18 local highlighting', () => {
  const baseRow: EarthquakeItem = {
    source: 'bgs',
    ts: 1748275200,
    magnitude: 3.5,
    depth_km: 10,
    place: 'London, UK',
  };

  it('renders is-local class when is_local=true', async () => {
    setEarthquakes([{ ...baseRow, is_local: true }]);
    const { container } = render(EarthquakeList);
    await tick();
    const row = container.querySelector('.quake-row');
    expect(row?.classList.contains('is-local')).toBe(true);
  });

  it('aria-label has Local event: prefix when is_local=true', async () => {
    setEarthquakes([{ ...baseRow, is_local: true }]);
    const { container } = render(EarthquakeList);
    await tick();
    const row = container.querySelector('.quake-row');
    expect(row?.getAttribute('aria-label')).toMatch(/^Local event:/);
  });

  it('does not add is-local class when is_local=false', async () => {
    setEarthquakes([{ ...baseRow, source: 'usgs', place: 'Chile', is_local: false } as EarthquakeItem]);
    const { container } = render(EarthquakeList);
    await tick();
    const row = container.querySelector('.quake-row');
    expect(row?.classList.contains('is-local')).toBe(false);
    expect(row?.getAttribute('aria-label') ?? '').not.toMatch(/^Local event:/);
  });

  it('treats undefined is_local as not-local (backward compat)', async () => {
    // Build a row WITHOUT is_local field at all
    const rowNoFlag: EarthquakeItem = { ...baseRow, source: 'usgs', place: 'Chile' };
    setEarthquakes([rowNoFlag]);
    const { container } = render(EarthquakeList);
    await tick();
    const row = container.querySelector('.quake-row');
    expect(row?.classList.contains('is-local')).toBe(false);
  });
});
