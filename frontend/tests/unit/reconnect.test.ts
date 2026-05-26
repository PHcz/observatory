import { describe, it, expect } from 'vitest';
import { nextBackoffMs } from '$lib/api/reconnect';

const cfg = { baseMs: 1000, capMs: 30000 };

describe('nextBackoffMs', () => {
  it('attempt 0 → 1000', () => expect(nextBackoffMs(0, cfg)).toBe(1000));
  it('attempt 1 → 2000', () => expect(nextBackoffMs(1, cfg)).toBe(2000));
  it('attempt 2 → 4000', () => expect(nextBackoffMs(2, cfg)).toBe(4000));
  it('attempt 3 → 8000', () => expect(nextBackoffMs(3, cfg)).toBe(8000));
  it('attempt 4 → 16000', () => expect(nextBackoffMs(4, cfg)).toBe(16000));
  it('attempt 5 → 30000 (capped)', () => expect(nextBackoffMs(5, cfg)).toBe(30000));
  it('attempt 10 → 30000 (still capped)', () => expect(nextBackoffMs(10, cfg)).toBe(30000));
});
