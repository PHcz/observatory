import { writable, type Writable } from 'svelte/store';
import type { LightningSummary } from '$lib/types';

export interface LightningState {
  summary: LightningSummary | null;
  hourlyBuckets: number[];
  lastUpdateTs: number | null;
}

export const lightningStore: Writable<LightningState> = writable({
  summary: null,
  hourlyBuckets: [],
  lastUpdateTs: null,
});
