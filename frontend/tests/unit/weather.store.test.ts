import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { weatherStore, setWeather, seedWeatherHistory, maxLuxToday } from '$lib/stores/weather';
import type { WeatherData, WeatherPoint } from '$lib/types';

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
    // History carries ALL sensor fields so the pressure/humidity/light charts
    // get live data, not just temperature.
    expect(state.history[0]).toEqual({
      ts: 1_000_000,
      temp_c: 20.5,
      humidity_pct: 50,
      pressure_hpa: 1013,
      lux: 100,
    });
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

describe('maxLuxToday (UI-13)', () => {
  beforeEach(() => {
    weatherStore.set({ current: null, history: [], lastUpdateTs: null });
  });

  it('returns null when history is empty', () => {
    expect(get(maxLuxToday)).toBeNull();
  });

  it('returns the max lux value from today', () => {
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    const t = Math.floor(todayStart.getTime() / 1000);
    seedWeatherHistory([
      { ts: t + 3600, temp_c: 12, lux: 5000 } as WeatherPoint,
      { ts: t + 7200, temp_c: 14, lux: 12000 } as WeatherPoint,
      { ts: t + 10800, temp_c: 15, lux: 8000 } as WeatherPoint,
    ]);
    expect(get(maxLuxToday)).toBe(12000);
  });

  it('excludes yesterday from the max', () => {
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    const t = Math.floor(todayStart.getTime() / 1000);
    seedWeatherHistory([
      { ts: t - 7200, temp_c: 10, lux: 50000 } as WeatherPoint, // yesterday — exclude
      { ts: t + 3600, temp_c: 12, lux: 5000 } as WeatherPoint, // today
    ]);
    expect(get(maxLuxToday)).toBe(5000);
  });

  it('ignores null lux readings', () => {
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    const t = Math.floor(todayStart.getTime() / 1000);
    seedWeatherHistory([
      { ts: t + 3600, temp_c: 12, lux: null } as WeatherPoint,
      { ts: t + 7200, temp_c: 14, lux: 800 } as WeatherPoint,
    ]);
    expect(get(maxLuxToday)).toBe(800);
  });

  it('returns null when today has only null lux', () => {
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    const t = Math.floor(todayStart.getTime() / 1000);
    seedWeatherHistory([
      { ts: t + 3600, temp_c: 12, lux: null } as WeatherPoint,
    ]);
    expect(get(maxLuxToday)).toBeNull();
  });
});
