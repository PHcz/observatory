import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { tsToLocalTime, ageSeconds, ageMinutes, formatAgeCaption } from '$lib/utils/time';

describe('time utilities', () => {
  describe('tsToLocalTime', () => {
    it('formats epoch seconds to HH:MM 24h string', () => {
      // 2024-01-01 14:32:00 UTC = 1704116520
      const result = tsToLocalTime(1704116520);
      // Result depends on local timezone, but must be a HH:MM pattern
      expect(result).toMatch(/^\d{2}:\d{2}$/);
    });
  });

  describe('ageSeconds', () => {
    it('returns positive age for past timestamp', () => {
      const nowSec = Math.floor(Date.now() / 1000);
      const pastTs = nowSec - 600;
      expect(ageSeconds(pastTs)).toBeGreaterThanOrEqual(599);
      expect(ageSeconds(pastTs)).toBeLessThanOrEqual(601);
    });

    it('returns 0 for future timestamp (non-negative)', () => {
      const futureTs = Math.floor(Date.now() / 1000) + 100;
      expect(ageSeconds(futureTs)).toBe(0);
    });
  });

  describe('ageMinutes', () => {
    it('returns floor of ageSeconds / 60', () => {
      const nowSec = Math.floor(Date.now() / 1000);
      const pastTs = nowSec - 600; // exactly 10 minutes
      expect(ageMinutes(pastTs)).toBe(10);
    });
  });

  describe('formatAgeCaption', () => {
    it('returns "X min ago" for < 60min', () => {
      const nowSec = Math.floor(Date.now() / 1000);
      const pastTs = nowSec - 300; // 5 min ago
      expect(formatAgeCaption(pastTs)).toBe('5 min ago');
    });

    it('returns "Xh Ym ago" for >= 60min', () => {
      const nowSec = Math.floor(Date.now() / 1000);
      const pastTs = nowSec - 7800; // 130 min = 2h 10m
      expect(formatAgeCaption(pastTs)).toBe('2h 10m ago');
    });

    it('returns "1h 0m ago" for exactly 60 min', () => {
      const nowSec = Math.floor(Date.now() / 1000);
      const pastTs = nowSec - 3600;
      expect(formatAgeCaption(pastTs)).toBe('1h 0m ago');
    });
  });
});
