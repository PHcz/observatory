import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import StatsRow from '$lib/panels/StatsRow.svelte';
import { weatherStore } from '$lib/stores/weather';
import { muonStore } from '$lib/stores/muon';
import type { WeatherData } from '$lib/types';

describe('StatsRow', () => {
  it('renders four em-dashes when weather data is null', () => {
    weatherStore.set({ current: null, history: [], lastUpdateTs: null });
    muonStore.set({ current: null, history: [], rate: null, lastUpdateTs: null });
    const { getAllByText } = render(StatsRow);
    const dashes = getAllByText('—');
    expect(dashes.length).toBeGreaterThanOrEqual(4);
  });

  it('renders all four stat labels', () => {
    weatherStore.set({ current: null, history: [], lastUpdateTs: null });
    muonStore.set({ current: null, history: [], rate: null, lastUpdateTs: null });
    render(StatsRow);
    expect(screen.getByText('Pressure')).toBeTruthy();
    expect(screen.getByText('Humidity')).toBeTruthy();
    expect(screen.getByText('Muons')).toBeTruthy();
    expect(screen.getByText('LIGHT')).toBeTruthy();
  });

  it('renders pressure value when data available', async () => {
    weatherStore.set({ current: null, history: [], lastUpdateTs: null });
    muonStore.set({ current: null, history: [], rate: null, lastUpdateTs: null });
    render(StatsRow);
    const weatherData: WeatherData = { ts: 1000000, temp_c: 18, humidity_pct: 65, pressure_hpa: 1013, lux: 0 };
    weatherStore.set({ current: weatherData, history: [], lastUpdateTs: 1000000 });
    await tick();
    expect(screen.getByText('1013')).toBeTruthy();
  });

  it('renders humidity value when data available', async () => {
    weatherStore.set({ current: null, history: [], lastUpdateTs: null });
    muonStore.set({ current: null, history: [], rate: null, lastUpdateTs: null });
    render(StatsRow);
    const weatherData: WeatherData = { ts: 1000000, temp_c: 18, humidity_pct: 65, pressure_hpa: 1013, lux: 0 };
    weatherStore.set({ current: weatherData, history: [], lastUpdateTs: 1000000 });
    await tick();
    expect(screen.getByText('65')).toBeTruthy();
  });

  it('renders muon rate when available', async () => {
    weatherStore.set({ current: null, history: [], lastUpdateTs: null });
    muonStore.set({ current: null, history: [], rate: null, lastUpdateTs: null });
    render(StatsRow);
    muonStore.set({ current: null, history: [], rate: 42, lastUpdateTs: 1000000 });
    await tick();
    expect(screen.getByText('42')).toBeTruthy();
  });

  it('renders dew point meta when both temp and humidity present', async () => {
    weatherStore.set({ current: null, history: [], lastUpdateTs: null });
    muonStore.set({ current: null, history: [], rate: null, lastUpdateTs: null });
    render(StatsRow);
    const weatherData: WeatherData = { ts: 1000000, temp_c: 20, humidity_pct: 50, pressure_hpa: 1013, lux: 0 };
    weatherStore.set({ current: weatherData, history: [], lastUpdateTs: 1000000 });
    await tick();
    // Should show dew point in meta
    const metaEl = document.querySelector('.stat-meta');
    expect(metaEl).toBeTruthy();
  });
});
