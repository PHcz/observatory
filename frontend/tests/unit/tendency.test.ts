import { describe, it, expect } from 'vitest';
import { tendency } from '$lib/utils/tendency';
import type { WeatherPoint } from '$lib/types';

const H = 3600;

// Build 4h of hourly points ending just before `nowTs`, with a linear ramp.
function ramp(nowTs: number, field: 'pressure_hpa' | 'humidity_pct', from: number, to: number): WeatherPoint[] {
  const pts: WeatherPoint[] = [];
  for (let i = 4; i >= 1; i--) {
    const frac = (4 - i) / 4;
    pts.push({ ts: nowTs - i * H, [field]: from + (to - from) * frac } as WeatherPoint);
  }
  return pts;
}

describe('tendency', () => {
  const now = 1_700_000_000;

  it('rising when value climbed > threshold over 3h', () => {
    const hist = ramp(now, 'pressure_hpa', 1000, 1006); // ~+1.5/h
    expect(tendency(hist, 'pressure_hpa', 1006, now, 1.0)).toBe('rising');
  });

  it('falling when value dropped > threshold over 3h', () => {
    const hist = ramp(now, 'pressure_hpa', 1010, 1004);
    expect(tendency(hist, 'pressure_hpa', 1004, now, 1.0)).toBe('falling');
  });

  it('steady when change within ±threshold', () => {
    const hist = ramp(now, 'pressure_hpa', 1013.0, 1013.4);
    expect(tendency(hist, 'pressure_hpa', 1013.4, now, 1.0)).toBe('steady');
  });

  it('steady when not enough history (< minSpanSec)', () => {
    const hist: WeatherPoint[] = [{ ts: now - 600, pressure_hpa: 990 } as WeatherPoint]; // 10 min only
    expect(tendency(hist, 'pressure_hpa', 1000, now, 1.0)).toBe('steady');
  });

  it('steady when no usable history', () => {
    expect(tendency([], 'humidity_pct', 60, now, 5)).toBe('steady');
  });

  it('humidity rising with its own threshold', () => {
    const hist = ramp(now, 'humidity_pct', 50, 70);
    expect(tendency(hist, 'humidity_pct', 70, now, 5)).toBe('rising');
  });
});
