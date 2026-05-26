import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { get } from 'svelte/store';
import { wsStatus, initWs, routeMessage } from '$lib/stores/ws';
import { weatherStore } from '$lib/stores/weather';
import { muonStore } from '$lib/stores/muon';
import { spaceWeatherStore } from '$lib/stores/spaceWeather';
import { lightningStore } from '$lib/stores/lightning';
import { auroraStore } from '$lib/stores/aurora';
import { earthquakeStore } from '$lib/stores/earthquakes';

// Mock WebSocket
class MockWs {
  static OPEN = 1;
  static CLOSED = 3;
  readyState = MockWs.OPEN;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((evt: { data: string }) => void) | null = null;
  sentMessages: string[] = [];

  send(data: string) { this.sentMessages.push(data); }
  close() { this.readyState = MockWs.CLOSED; }

  simulateOpen() { this.onopen?.(); }
  simulateMessage(data: unknown) { this.onmessage?.({ data: JSON.stringify(data) }); }
  simulateClose() { this.onclose?.(); }
  simulateError() { this.onerror?.(); }
}

let mockWsInstance: MockWs;

beforeEach(() => {
  vi.useFakeTimers();
  mockWsInstance = new MockWs();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const WsMock: any = vi.fn(() => mockWsInstance);
  WsMock.OPEN = MockWs.OPEN;
  WsMock.CLOSED = MockWs.CLOSED;
  vi.stubGlobal('WebSocket', WsMock);
  vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173' });

  // Reset stores
  wsStatus.set('connecting');
  weatherStore.set({ current: null, history: [], lastUpdateTs: null });
  muonStore.set({ current: null, history: [], rate: null, lastUpdateTs: null });
  spaceWeatherStore.set({ current: null, lastUpdateTs: null });
  lightningStore.set({ summary: null, hourlyBuckets: [], lastUpdateTs: null });
  auroraStore.set({ current: null, lastUpdateTs: null });
  earthquakeStore.set({ recent: [], lastUpdateTs: null });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('WS store — connection lifecycle', () => {
  it('sets status to connected on open', () => {
    const cleanup = initWs();
    mockWsInstance.simulateOpen();
    expect(get(wsStatus)).toBe('connected');
    cleanup();
  });

  it('sets status to disconnected on close', () => {
    const cleanup = initWs();
    mockWsInstance.simulateOpen();
    mockWsInstance.simulateClose();
    expect(get(wsStatus)).toBe('disconnected');
    cleanup();
  });

  it('schedules reconnect timer on close', () => {
    const cleanup = initWs();
    mockWsInstance.simulateOpen();
    mockWsInstance.simulateClose();
    // Timer should be scheduled
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    cleanup();
  });

  it('cleanup cancels reconnect timer', () => {
    const cleanup = initWs();
    mockWsInstance.simulateOpen();
    mockWsInstance.simulateClose();
    cleanup();
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe('WS store — message routing', () => {
  it('routes weather envelope to weatherStore', () => {
    const data = { ts: 1000, temp_c: 20.5, humidity_pct: 60, pressure_hpa: 1013, lux: 100 };
    routeMessage(JSON.stringify({ type: 'weather', data }));
    expect(get(weatherStore).current).toMatchObject({ temp_c: 20.5 });
  });

  it('routes muon envelope to muonBuffer', () => {
    // buffer event then flush
    const evt = { ts: 1000, latest_event_ts: 1000, detector_pressure_hpa: null, detector_temp_c: null };
    routeMessage(JSON.stringify({ type: 'muon', data: evt }));
    // bufferMuonEvent is called; history only populated after flush
    // we don't flush here — just verify no crash
  });

  it('routes space_weather envelope', () => {
    const data = { ts: 1000, kp_index: 3.5, solar_wind_kms: 450, flare_class: 'C1.2', flare_peak_ts: null };
    routeMessage(JSON.stringify({ type: 'space_weather', data }));
    expect(get(spaceWeatherStore).current).toMatchObject({ kp_index: 3.5 });
  });

  it('routes lightning envelope', () => {
    const data = { ts: 1000, past_hour: 5, past_24h: 20, nearest_km: 15, total_today: 25 };
    routeMessage(JSON.stringify({ type: 'lightning', data }));
    expect(get(lightningStore).summary).toMatchObject({ past_hour: 5 });
  });

  it('routes aurora envelope', () => {
    const data = { ts: 1000, status: 'green', detail: null };
    routeMessage(JSON.stringify({ type: 'aurora', data }));
    expect(get(auroraStore).current).toMatchObject({ status: 'green' });
  });

  it('routes earthquake envelope — prepends to recent', () => {
    const eq = { ts: 1000, source: 'usgs', magnitude: 5.2, place: 'Test place', depth_km: 10 };
    routeMessage(JSON.stringify({ type: 'earthquake', data: eq }));
    expect(get(earthquakeStore).recent).toHaveLength(1);
    expect(get(earthquakeStore).recent[0]).toMatchObject({ magnitude: 5.2 });
  });

  it('routes snapshot envelope to all per-source stores', () => {
    const snap = {
      timestamp: 1000,
      astronomy: null,
      weather: { freshness: 'healthy', data: { ts: 1000, temp_c: 15.5, humidity_pct: 70, pressure_hpa: 1010, lux: 200 } },
      muon: { freshness: 'healthy', data: { latest_event_ts: 900, detector_pressure_hpa: 1010, detector_temp_c: 20 } },
      space_weather: { freshness: 'healthy', data: { ts: 1000, kp_index: 2.0, solar_wind_kms: 400, flare_class: null, flare_peak_ts: null } },
      lightning_summary: { freshness: 'healthy', data: { ts: 1000, past_hour: 0, past_24h: 0, nearest_km: null, total_today: 0 } },
      aurora: { freshness: 'healthy', data: { ts: 1000, status: 'green', detail: null } },
      earthquakes_recent: [{ ts: 900, source: 'usgs', magnitude: 4.1, place: 'Somewhere', depth_km: 20 }],
    };
    routeMessage(JSON.stringify({ type: 'snapshot', data: snap }));
    expect(get(weatherStore).current?.temp_c).toBe(15.5);
    expect(get(spaceWeatherStore).current?.kp_index).toBe(2.0);
    expect(get(auroraStore).current?.status).toBe('green');
    expect(get(earthquakeStore).recent).toHaveLength(1);
  });

  it('replies pong to ping', () => {
    const cleanup = initWs();
    mockWsInstance.simulateOpen();
    // Simulate ping via routeMessage using the module-level ws reference
    // Need to trigger via onmessage handler
    mockWsInstance.simulateMessage({ type: 'ping', ts: 1000 });
    expect(mockWsInstance.sentMessages).toContain(JSON.stringify({ type: 'pong' }));
    cleanup();
  });

  it('ignores malformed JSON without throwing', () => {
    expect(() => routeMessage('not-json')).not.toThrow();
  });
});

describe('WS store — reconnect backoff', () => {
  it('reconnects after close with delay', () => {
    const WsConstructor = vi.fn(() => mockWsInstance);
    vi.stubGlobal('WebSocket', WsConstructor);

    const cleanup = initWs();
    mockWsInstance.simulateOpen();
    mockWsInstance.simulateClose();

    const callCount = WsConstructor.mock.calls.length; // 1 (initial)
    // Advance timer past 1s first backoff
    vi.advanceTimersByTime(1100);
    expect(WsConstructor.mock.calls.length).toBeGreaterThan(callCount);

    cleanup();
  });
});

describe('WS store — browser offline/online events', () => {
  it('marks status disconnected immediately on offline event', () => {
    const cleanup = initWs();
    mockWsInstance.simulateOpen();
    expect(get(wsStatus)).toBe('connected');

    window.dispatchEvent(new Event('offline'));

    expect(get(wsStatus)).toBe('disconnected');
    expect(mockWsInstance.readyState).toBe(MockWs.CLOSED);
    cleanup();
  });

  it('triggers immediate reconnect on online event (no backoff wait)', () => {
    const cleanup = initWs();
    mockWsInstance.simulateOpen();

    window.dispatchEvent(new Event('offline'));
    expect(get(wsStatus)).toBe('disconnected');

    // Capture how many WebSocket constructions had happened.
    // The WebSocket factory in beforeEach is a vi.fn; call count is the proxy.
    const WsFactory = (globalThis as unknown as { WebSocket: ReturnType<typeof vi.fn> }).WebSocket;
    const callsBeforeOnline = WsFactory.mock.calls.length;

    window.dispatchEvent(new Event('online'));

    // Online should immediately open a new socket (not schedule a backoff timer first).
    expect(WsFactory.mock.calls.length).toBeGreaterThan(callsBeforeOnline);
    cleanup();
  });

  it('removes offline/online listeners on cleanup', () => {
    const cleanup = initWs();
    mockWsInstance.simulateOpen();
    cleanup();

    // Reset status to something distinct so we can assert listener removal.
    wsStatus.set('connected');
    window.dispatchEvent(new Event('offline'));
    // Listener was removed by cleanup, so status must NOT flip back to 'disconnected'.
    expect(get(wsStatus)).toBe('connected');
  });
});
