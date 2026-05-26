export type StalenessLevel = 'fresh' | 'amber' | 'red';

/**
 * Default panel-level staleness threshold (seconds) used when the
 * /api/health payload omits or zeros `staleness_threshold_sec` for a source.
 * 300s (5 min) matches the human "freshness intuition" for live-update panels —
 * brief network or polling-cycle gaps shouldn't trip the panel into amber.
 */
export const DEFAULT_STALENESS_THRESHOLD_SEC = 300;

export function deriveStaleness(ageSec: number, thresholdSec: number): StalenessLevel {
  if (!isFinite(ageSec) || !isFinite(thresholdSec) || thresholdSec <= 0 || ageSec < 0) return 'red';
  if (ageSec < thresholdSec) return 'fresh';
  if (ageSec < thresholdSec * 2.5) return 'amber';
  return 'red';
}

export function stalenessToDot(level: StalenessLevel): 'green' | 'amber' | 'red' {
  return level === 'fresh' ? 'green' : level;
}
