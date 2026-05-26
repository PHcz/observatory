import { writable, type Writable } from 'svelte/store';
import type { AstronomyData } from '$lib/types';

export const astronomyStore: Writable<AstronomyData | null> = writable(null);

export function setAstronomy(data: AstronomyData): void {
  astronomyStore.set(data);
}
