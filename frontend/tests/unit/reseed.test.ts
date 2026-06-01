import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { startReseed } from '$lib/utils/reseed';

/**
 * Regression test for the muon/weather chart live-accumulation drift bug.
 *
 * Before this fix, charts seeded from the server exactly once (on mount) and
 * thereafter trusted their own lossy WebSocket accumulation — so a backgrounded
 * tab / sleeping device / dropped WS frames produced spurious near-zero spikes
 * in the raw layer that compounded over an unrefreshed session. The fix:
 * reconcile with the server periodically AND when the tab becomes visible.
 *
 * These tests would FAIL before the fix (no second reseed ever happened).
 */
describe('startReseed', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    // reset visibility to default
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    });
  });

  function setVisibility(state: 'visible' | 'hidden') {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => state,
    });
    document.dispatchEvent(new Event('visibilitychange'));
  }

  it('calls reseed on the interval (repeatedly)', () => {
    const reseed = vi.fn();
    const stop = startReseed(reseed, 300_000);
    expect(reseed).toHaveBeenCalledTimes(0); // does not fire immediately
    vi.advanceTimersByTime(300_000);
    expect(reseed).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(300_000);
    expect(reseed).toHaveBeenCalledTimes(2);
    stop();
  });

  it('calls reseed when the tab becomes visible', () => {
    const reseed = vi.fn();
    const stop = startReseed(reseed, 300_000);
    setVisibility('visible');
    expect(reseed).toHaveBeenCalledTimes(1);
    stop();
  });

  it('does NOT reseed when the tab becomes hidden', () => {
    const reseed = vi.fn();
    const stop = startReseed(reseed, 300_000);
    setVisibility('hidden');
    expect(reseed).toHaveBeenCalledTimes(0);
    stop();
  });

  it('stop() clears the interval and removes the visibility listener', () => {
    const reseed = vi.fn();
    const stop = startReseed(reseed, 300_000);
    stop();
    vi.advanceTimersByTime(900_000);
    setVisibility('visible');
    expect(reseed).toHaveBeenCalledTimes(0);
  });
});
