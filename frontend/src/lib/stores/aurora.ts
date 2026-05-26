import { writable, type Writable } from 'svelte/store';
import type { AuroraData } from '$lib/types';

export interface AuroraState {
  current: AuroraData | null;
  lastUpdateTs: number | null;
}

export const auroraStore: Writable<AuroraState> = writable({
  current: null,
  lastUpdateTs: null,
});
