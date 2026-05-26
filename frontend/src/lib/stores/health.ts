import { writable, type Writable } from 'svelte/store';
import type { HealthResponse } from '$lib/types';

export interface HealthState {
  data: HealthResponse | null;
  lastFetchTs: number | null;
}

export const healthStore: Writable<HealthState> = writable({
  data: null,
  lastFetchTs: null,
});
