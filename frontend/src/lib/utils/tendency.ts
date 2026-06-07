import type { WeatherPoint } from '$lib/types';

export type Trend = 'rising' | 'steady' | 'falling';

/**
 * Qualitative trend of a weather field over the last `windowSec` (default 3h),
 * comparing the current value against the reading closest to `nowTs - windowSec`.
 *
 * Returns 'steady' when there isn't enough history yet (oldest reading younger
 * than `minSpanSec`) or the change is within ±`threshold`. This replaces the
 * previously-hardcoded "steady" label so the stat reads honestly.
 */
export function tendency(
  history: WeatherPoint[],
  field: 'pressure_hpa' | 'humidity_pct',
  nowVal: number,
  nowTs: number,
  threshold: number,
  windowSec = 3 * 3600,
  minSpanSec = 3600,
): Trend {
  const pts = history.filter((p) => p[field] != null && p.ts < nowTs);
  if (pts.length === 0) return 'steady';
  const oldest = pts.reduce((a, b) => (a.ts < b.ts ? a : b));
  if (nowTs - oldest.ts < minSpanSec) return 'steady'; // too little history to judge
  const target = nowTs - windowSec;
  const past = pts.reduce((a, b) =>
    Math.abs(a.ts - target) <= Math.abs(b.ts - target) ? a : b,
  );
  const delta = nowVal - (past[field] as number);
  if (delta > threshold) return 'rising';
  if (delta < -threshold) return 'falling';
  return 'steady';
}
