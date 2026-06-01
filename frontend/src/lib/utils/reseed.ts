/**
 * Periodic + visibility-driven re-seed for live charts.
 *
 * The muon/weather charts seed their 24h history from the server once (on
 * mount) and are then maintained by accumulating WebSocket events client-side.
 * That live stream is lossy: a backgrounded/throttled tab, a sleeping device,
 * a wifi blip, or a WS disconnect→reconnect drops events, leaving per-minute
 * buckets missing or under-counted. The raw chart layer renders those as
 * spurious near-zero spikes that compound the longer the tab is left open
 * (the clean seed data scrolls out of the 24h window and is replaced by lossy
 * live buckets).
 *
 * The server's SQLite is the source of truth, so the client must RECONCILE
 * with it rather than trust its own accumulation. This helper re-runs the
 * caller's `reseed` (a fetch-history + seed-store) on a timer AND whenever the
 * tab becomes visible again (which directly covers the laptop-sleep /
 * backgrounded-tab case). The 1s live append still provides sub-poll freshness
 * on top of each reconciled baseline.
 *
 * Returns a stop() that clears the timer and removes the listener — call it in
 * the component's onDestroy.
 */
export const DEFAULT_RESEED_INTERVAL_MS = 300_000; // 5 minutes

export function startReseed(
  reseed: () => void,
  intervalMs: number = DEFAULT_RESEED_INTERVAL_MS,
): () => void {
  const id = setInterval(reseed, intervalMs);

  const onVisibility = () => {
    if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
      reseed();
    }
  };

  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibility);
  }

  return () => {
    clearInterval(id);
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', onVisibility);
    }
  };
}
