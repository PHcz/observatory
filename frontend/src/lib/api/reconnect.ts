export interface BackoffConfig { baseMs: number; capMs: number; }

export function nextBackoffMs(attempt: number, cfg: BackoffConfig): number {
  const delay = cfg.baseMs * (2 ** attempt);
  return Math.min(delay, cfg.capMs);
}
