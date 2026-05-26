export type StalenessLevel = 'fresh' | 'amber' | 'red';

export function deriveStaleness(ageSec: number, thresholdSec: number): StalenessLevel {
  if (!isFinite(ageSec) || !isFinite(thresholdSec) || thresholdSec <= 0 || ageSec < 0) return 'red';
  if (ageSec < thresholdSec) return 'fresh';
  if (ageSec < thresholdSec * 2.5) return 'amber';
  return 'red';
}

export function stalenessToDot(level: StalenessLevel): 'green' | 'amber' | 'red' {
  return level === 'fresh' ? 'green' : level;
}
