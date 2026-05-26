import { writable, type Writable } from 'svelte/store';
import type { WeatherData, WeatherPoint } from '$lib/types';

export interface WeatherState {
  current: WeatherData | null;
  history: WeatherPoint[];
  lastUpdateTs: number | null;
}

export const weatherStore: Writable<WeatherState> = writable({
  current: null,
  history: [],
  lastUpdateTs: null,
});

export function setWeather(data: WeatherData): void {
  weatherStore.update(s => ({ ...s, current: data, lastUpdateTs: Math.floor(Date.now() / 1000) }));
}

export function seedWeatherHistory(points: WeatherPoint[]): void {
  weatherStore.update(s => ({ ...s, history: points }));
}
