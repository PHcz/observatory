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
