import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { get } from 'svelte/store';
import { wsStatus, initWs } from '$lib/stores/ws';

// Mock WebSocket — mirrors tests/unit/ws.store.test.ts pattern, with closeSpy
class MockWs {
  static OPEN = 1;
  static CLOSED = 3;
  readyState = MockWs.OPEN;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((evt: { data: string }) => void) | null = null;
  sentMessages: string[] = [];
  closeCount = 0;

  send(data: string) { this.sentMessages.push(data); }
  close() {
    this.closeCount += 1;
    this.readyState = MockWs.CLOSED;
  }

  simulateOpen() { this.onopen?.(); }
  simulateMessage(data: unknown) { this.onmessage?.({ data: JSON.stringify(data) }); }
  simulateClose() { this.onclose?.(); }
}

let mockInstances: MockWs[] = [];
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let WsConstructor: any;

beforeEach(() => {
  vi.useFakeTimers();
  mockInstances = [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  WsConstructor = vi.fn(() => {
    const m = new MockWs();
    mockInstances.push(m);
    return m;
  });
  WsConstructor.OPEN = MockWs.OPEN;
  WsConstructor.CLOSED = MockWs.CLOSED;
  vi.stubGlobal('WebSocket', WsConstructor);
  vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173' });
  wsStatus.set('connecting');
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('WS watchdog — inter-message silence detection', () => {
  it('Test 1: no messages for 60s -> disconnected and ws.close called', () => {
    const cleanup = initWs();
    const ws = mockInstances[0];
    ws.simulateOpen();
    expect(get(wsStatus)).toBe('connected');

    // Advance 59s — still connected (watchdog not fired)
    vi.advanceTimersByTime(59_000);
    expect(get(wsStatus)).toBe('connected');
    expect(ws.closeCount).toBe(0);

    // Advance another 1.001s — total 60.001s — watchdog fires but reconnect
    // backoff (1000ms after watchdog) has not yet re-set state to 'connecting'
    vi.advanceTimersByTime(1_001);
    expect(get(wsStatus)).toBe('disconnected');
    expect(ws.closeCount).toBeGreaterThanOrEqual(1);

    cleanup();
  });

  it('Test 2: ping message resets watchdog timer', () => {
    const cleanup = initWs();
    const ws = mockInstances[0];
    ws.simulateOpen();

    // Send a ping at t=30s
    vi.advanceTimersByTime(30_000);
    ws.simulateMessage({ type: 'ping', ts: 1000 });

    // Advance to t=85s — 55s since last message — still connected
    vi.advanceTimersByTime(55_000);
    expect(get(wsStatus)).toBe('connected');

    // Advance to t=90.001s — watchdog fires (60s after ping) but reconnect
    // backoff (+1000ms) has not yet bumped state back to 'connecting'
    vi.advanceTimersByTime(5_001);
    expect(get(wsStatus)).toBe('disconnected');

    cleanup();
  });

  it('Test 3: non-ping (muon) message also resets watchdog', () => {
    const cleanup = initWs();
    const ws = mockInstances[0];
    ws.simulateOpen();

    vi.advanceTimersByTime(30_000);
    ws.simulateMessage({
      type: 'muon',
      data: { ts: 1000, latest_event_ts: 1000, detector_pressure_hpa: null, detector_temp_c: null }
    });

    vi.advanceTimersByTime(55_000);
    expect(get(wsStatus)).toBe('connected');

    // Watchdog fires at t=90s (60s after muon msg); assert before reconnect at t=91s
    vi.advanceTimersByTime(5_001);
    expect(get(wsStatus)).toBe('disconnected');

    cleanup();
  });

  it('Test 4: initWs cleanup clears watchdog — no late mutation', () => {
    const cleanup = initWs();
    const ws = mockInstances[0];
    ws.simulateOpen();
    expect(get(wsStatus)).toBe('connected');

    cleanup();
    // Set sentinel to detect any unwanted change
    wsStatus.set('connecting');

    // Advance well past the watchdog window
    vi.advanceTimersByTime(120_000);

    // Status was set to 'connecting' after cleanup; should NOT have been mutated
    expect(get(wsStatus)).toBe('connecting');
  });

  it('Test 5: after watchdog fires, reconnect restores connected on next onopen', () => {
    const cleanup = initWs();
    const ws1 = mockInstances[0];
    ws1.simulateOpen();
    expect(get(wsStatus)).toBe('connected');

    // Silence triggers watchdog at t=60s; assert before reconnect at t=61s
    vi.advanceTimersByTime(60_001);
    expect(get(wsStatus)).toBe('disconnected');

    // Advance past reconnect backoff (fires at t=61s; we're at t=60.001s)
    vi.advanceTimersByTime(2_000);

    // A new WS should have been constructed
    expect(WsConstructor.mock.calls.length).toBeGreaterThanOrEqual(2);
    const ws2 = mockInstances[mockInstances.length - 1];
    ws2.simulateOpen();
    expect(get(wsStatus)).toBe('connected');

    cleanup();
  });
});
