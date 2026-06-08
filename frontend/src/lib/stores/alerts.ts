import { writable, type Writable } from 'svelte/store';
import type { AlertRow } from '$lib/types';
import { fetchAlerts } from '$lib/api/rest';

export interface AlertsState {
  active: AlertRow[];
  recent: AlertRow[];
}

export const alertsStore: Writable<AlertsState> = writable({
  active: [],
  recent: [],
});

// 30-second poll interval (UI-SPEC §Alert store)
const ALERTS_POLL_MS = 30 * 1000;
let alertsTimer: ReturnType<typeof setInterval> | null = null;

async function pollOnce(): Promise<void> {
  try {
    const data = await fetchAlerts();
    alertsStore.set({ active: data.active ?? [], recent: data.recent ?? [] });
  } catch {
    // Swallow — panel shows empty state on fetch failure; no alert noise.
  }
}

/**
 * Immediately re-fetch alerts. Called by the WS layer when a
 * {type:"alert"} message arrives (same immediate-refetch pattern
 * as weather/muon stores on their WS push).
 */
export function refetchAlerts(): void {
  void pollOnce();
}

export function initAlertsPolling(): () => void {
  void pollOnce();
  alertsTimer = setInterval(() => {
    void pollOnce();
  }, ALERTS_POLL_MS);
  return () => {
    if (alertsTimer) {
      clearInterval(alertsTimer);
      alertsTimer = null;
    }
  };
}
