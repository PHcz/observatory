import { describe, it, expect } from 'vitest';
import { nextBackoffMs } from '$lib/api/reconnect';

describe('nextBackoffMs', () => {
  it('returns base at attempt 0', () => {
    expect(nextBackoffMs(0, { baseMs: 1000, capMs: 30000 })).toBe(1000);
  });
  it('caps at capMs', () => {
    expect(nextBackoffMs(5, { baseMs: 1000, capMs: 30000 })).toBe(30000);
  });
});
