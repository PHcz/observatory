import { describe, it, expect } from 'vitest';
import { recentMeanRate } from '$lib/stores/muon';
import type { MuonPoint } from '$lib/types';

describe('recentMeanRate (StatsRow muon number — server-reconciled, no rolling-window undercount)', () => {
  const NOW = 1_000_000; // currentMinuteStart = floor(1_000_000/60)*60 = 999_960

  it('returns null for empty history', () => {
    expect(recentMeanRate([], NOW)).toBeNull();
  });

  it('averages the last N COMPLETE minute buckets, excluding the in-progress minute', () => {
    const history: MuonPoint[] = [
      { ts: 999_600, rate_per_min: 100 },
      { ts: 999_660, rate_per_min: 110 },
      { ts: 999_720, rate_per_min: 120 },
      { ts: 999_780, rate_per_min: 130 },
      { ts: 999_840, rate_per_min: 140 },
      { ts: 999_900, rate_per_min: 150 }, // last complete minute
      { ts: 999_960, rate_per_min: 5 },   // in-progress current minute → MUST be excluded
    ];
    // last 5 complete = [110,120,130,140,150] → mean 130 (the partial 5 is ignored)
    expect(recentMeanRate(history, NOW, 5)).toBeCloseTo(130, 6);
  });

  it('averages all available when fewer than N complete minutes', () => {
    const history: MuonPoint[] = [
      { ts: 999_780, rate_per_min: 120 },
      { ts: 999_840, rate_per_min: 180 },
    ];
    expect(recentMeanRate(history, NOW, 5)).toBeCloseTo(150, 6);
  });

  it('returns null when only the in-progress minute exists (no complete bucket)', () => {
    const history: MuonPoint[] = [{ ts: 999_960, rate_per_min: 3 }];
    expect(recentMeanRate(history, NOW, 5)).toBeNull();
  });
});
