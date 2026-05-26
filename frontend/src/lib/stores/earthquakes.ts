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
