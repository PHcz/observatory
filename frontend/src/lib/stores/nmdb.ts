import { writable, type Writable } from 'svelte/store';
import type { NmdbResponse } from '$lib/types';
import { fetchNmdb } from '$lib/api/rest';

export interface NmdbState {
  data: NmdbResponse | null;
  lastFetchTs: number | null;
}

export const nmdbStore: Writable<NmdbState> = writable({
  data: null,
  lastFetchTs: null,
});

/**
 * Replace the cached NMDB overlay snapshot. Used by the polling loop and by the
 * Wave-0 RED NmdbOverlayPanel test (which drives the panel via setNmdb).
 */
export function setNmdb(data: NmdbResponse | null): void {
  nmdbStore.set({ data, lastFetchTs: Math.floor(Date.now() / 1000) });
}

// The NMDB poller refreshes hourly; a 5-min UI poll keeps the overlay current
// without hammering the local endpoint (read-only SQLite, local-first).
const NMDB_POLL_MS = 5 * 60 * 1000;
let nmdbTimer: ReturnType<typeof setInterval> | null = null;

async function pollOnce(): Promise<void> {
  try {
    const data = await fetchNmdb();
    setNmdb(data);
  } catch {
    // Swallow — the panel shows its empty / stale state on fetch failure.
  }
}

export function initNmdbPolling(): () => void {
  void pollOnce();
  nmdbTimer = setInterval(() => {
    void pollOnce();
  }, NMDB_POLL_MS);
  return () => {
    if (nmdbTimer) {
      clearInterval(nmdbTimer);
      nmdbTimer = null;
    }
  };
}
