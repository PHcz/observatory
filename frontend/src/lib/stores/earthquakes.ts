import { writable, type Writable } from 'svelte/store';
import type { EarthquakeItem } from '$lib/types';

export interface EarthquakeState {
  recent: EarthquakeItem[];
  lastUpdateTs: number | null;
}

export const earthquakeStore: Writable<EarthquakeState> = writable({
  recent: [],
  lastUpdateTs: null,
});

export function prependEarthquake(e: EarthquakeItem): void {
  earthquakeStore.update(s => ({
    recent: [e, ...s.recent].slice(0, 50),
    lastUpdateTs: Math.floor(Date.now() / 1000),
  }));
}

export function setEarthquakes(list: EarthquakeItem[]): void {
  earthquakeStore.update(s => ({
    ...s,
    recent: list.slice(0, 50),
    lastUpdateTs: Math.floor(Date.now() / 1000),
  }));
}
