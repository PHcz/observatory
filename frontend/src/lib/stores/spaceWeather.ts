import { writable, type Writable } from 'svelte/store';
import type { SpaceWeatherData } from '$lib/types';

export interface SpaceWeatherState {
  current: SpaceWeatherData | null;
  lastUpdateTs: number | null;
}

export const spaceWeatherStore: Writable<SpaceWeatherState> = writable({
  current: null,
  lastUpdateTs: null,
});
