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

/**
 * Merge incoming lightning data into the existing summary.
 *
 * The snapshot path delivers a full LightningSummary (past_hour, past_24h,
 * nearest_km, total_today, ts). Per-event WS frames may carry only a partial
 * shape (e.g. just nearest_km + ts on a fresh strike). Merging — rather than
 * replacing — preserves aggregates across partial frames.
 *
 * See UAT gap 6 (07-UAT.md): the panel showed em-dashes because a partial
 * per-event frame wiped the snapshot aggregates.
 */
export function setLightning(data: Partial<LightningSummary>): void {
  lightningStore.update(s => ({
    ...s,
    summary: { ...(s.summary ?? {}), ...data } as LightningSummary,
    lastUpdateTs: Math.floor(Date.now() / 1000),
  }));
}
