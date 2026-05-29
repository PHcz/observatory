import { describe, it, expect, vi, afterEach } from 'vitest';
import { fetchMuonHistory, fetchWeatherHistory, fetchHealth } from '$lib/api/rest';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('REST history clients', () => {
  describe('fetchMuonHistory', () => {
    it('fetches /api/muon and maps rows to MuonPoint[]', async () => {
      const mockResponse = {
        window: { from: 0, to: 1000 },
        bucket_size_sec: 60,
        agg: 'minute',
        rows: [{ ts: 100, rate_per_min: 5 }],
      };
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockResponse,
      }));

      const result = await fetchMuonHistory(0, 1000);
      expect(result).toEqual([{ ts: 100, rate_per_min: 5 }]);
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/muon'),
        expect.any(Object),
      );
    });

    it('includes from and to query params', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ window: {}, bucket_size_sec: 60, agg: 'minute', rows: [] }),
      }));

      await fetchMuonHistory(1000, 2000);
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(url).toContain('from=1000');
      expect(url).toContain('to=2000');
    });
  });

  describe('fetchWeatherHistory', () => {
    it('fetches /api/weather and maps rows to WeatherPoint[]', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          window: { from: 0, to: 1000 },
          bucket_size_sec: 300,
          agg: 'minute',
          rows: [{ ts: 500, temp_c: 18.5, humidity_pct: 55, pressure_hpa: 1012, lux: 800 }],
        }),
      }));

      const result = await fetchWeatherHistory(0, 1000);
      // All four sensor fields must be carried so the pressure/humidity/light
      // charts get data — not just temp_c.
      expect(result).toEqual([
        { ts: 500, temp_c: 18.5, humidity_pct: 55, pressure_hpa: 1012, lux: 800 },
      ]);
    });

    it('maps missing sensor fields to null (not undefined)', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          window: { from: 0, to: 1000 },
          bucket_size_sec: 300,
          agg: 'minute',
          rows: [{ ts: 500, temp_c: 18.5 }],
        }),
      }));

      const result = await fetchWeatherHistory(0, 1000);
      expect(result).toEqual([
        { ts: 500, temp_c: 18.5, humidity_pct: null, pressure_hpa: null, lux: null },
      ]);
    });
  });

  describe('fetchHealth', () => {
    it('fetches /api/health and returns parsed JSON', async () => {
      const healthData = { timestamp: 1000, status: 'healthy', local: {}, external: {}, pi: {} };
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
        ok: true,
        json: async () => healthData,
      }));

      const result = await fetchHealth();
      expect(result).toEqual(healthData);
      const url = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(url).toBe('/api/health');
    });

    it('throws on non-ok response', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
      }));

      await expect(fetchHealth()).rejects.toThrow('HTTP 500');
    });
  });
});
