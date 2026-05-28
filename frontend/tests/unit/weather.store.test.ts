import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { weatherStore, setWeather, seedWeatherHistory } from '$lib/stores/weather';
import type { WeatherData } from '$lib/types';

const makeReading = (ts: number, temp: number | null = 20): WeatherData => ({
  ts,
  temp_c: temp,
  humidity_pct: 50,
  pressure_hpa: 1013,
  lux: 100,
});

describe('weatherStore.setWeather appends to history for live chart updates', () => {
  beforeEach(() => {
    weatherStore.set({ current: null, history: [], lastUpdateTs: null });
  });

  it('updates current AND appends a WeatherPoint to history on every call', () => {
    setWeather(makeReading(1_000_000, 20.5));
    const state = get(weatherStore);
    expect(state.current?.ts).toBe(1_000_000);
    expect(state.history).toHaveLength(1);
    expect(state.history[0]).toEqual({ ts: 1_000_000, temp_c: 20.5 });
  });

  it('dedups by ts when REST snapshot already has the live reading', () => {
    seedWeatherHistory([{ ts: 1_000_000, temp_c: 20.5 }]);
    setWeather(makeReading(1_000_000, 20.5));
    const state = get(weatherStore);
    expect(state.history).toHaveLength(1);
  });

  it('keeps history sorted ascending by ts', () => {
    const now = Math.floor(Date.now() / 1000);
    setWeather(makeReading(now - 200, 22.0));
    setWeather(makeReading(now - 100, 21.0)); // out of order
    setWeather(makeReading(now, 23.0));
    const state = get(weatherStore);
    expect(state.history.map(p => p.ts)).toEqual([now - 200, now - 100, now]);
  });

  it('trims history to 24h window so it does not grow unbounded', () => {
    const now = Math.floor(Date.now() / 1000);
    seedWeatherHistory([
      { ts: now - 100_000, temp_c: 10 }, // older than 24h — should drop
      { ts: now - 1_000, temp_c: 20 }, // within window
    ]);
    setWeather(makeReading(now, 25));
    const state = get(weatherStore);
    // The 100k-old point is dropped; the 1k-old + new are kept
    expect(state.history.map(p => p.ts)).toEqual([now - 1_000, now]);
  });

  it('preserves null temp_c (sensor failure) in history', () => {
    setWeather(makeReading(1_000_000, null));
    const state = get(weatherStore);
    expect(state.history[0].temp_c).toBeNull();
  });
});
