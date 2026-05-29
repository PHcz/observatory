import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';
import { settingsStore } from '$lib/stores/settings';
import { DEFAULTS } from '$lib/utils/settingsSchema';

describe('settingsStore', () => {
  beforeEach(() => {
    localStorage.clear();
    settingsStore.resetToDefaults();
    vi.useRealTimers();
  });

  it('initial value matches DEFAULTS when localStorage empty', () => {
    expect(get(settingsStore)).toEqual(DEFAULTS);
  });

  it('set() updates the store synchronously', () => {
    const next = { ...DEFAULTS, theme: 'dark' as const };
    settingsStore.set(next);
    expect(get(settingsStore)).toEqual(next);
  });

  it('schedules localStorage write after exactly 100ms', () => {
    vi.useFakeTimers();
    localStorage.clear();
    const next = { ...DEFAULTS, theme: 'dark' as const };
    settingsStore.set(next);

    vi.advanceTimersByTime(99);
    expect(localStorage.getItem('observatory.settings.v1')).toBeNull();

    vi.advanceTimersByTime(1);
    const written = localStorage.getItem('observatory.settings.v1');
    expect(written).not.toBeNull();
    expect(JSON.parse(written as string).theme).toBe('dark');
  });

  it('coalesces two rapid set() calls into one write 100ms after the last', () => {
    vi.useFakeTimers();
    localStorage.clear();
    settingsStore.set({ ...DEFAULTS, theme: 'dark' as const });
    vi.advanceTimersByTime(50);
    settingsStore.set({ ...DEFAULTS, theme: 'light' as const });
    vi.advanceTimersByTime(99);
    expect(localStorage.getItem('observatory.settings.v1')).toBeNull();
    vi.advanceTimersByTime(1);
    const written = localStorage.getItem('observatory.settings.v1');
    expect(JSON.parse(written as string).theme).toBe('light');
  });

  it('resetToDefaults restores theme=auto and all panels true', () => {
    settingsStore.set({ ...DEFAULTS, theme: 'dark' as const, panels: { ...DEFAULTS.panels, lightning: false } });
    settingsStore.resetToDefaults();
    const v = get(settingsStore);
    expect(v.theme).toBe('auto');
    expect(Object.values(v.panels).every((p) => p === true)).toBe(true);
  });
});
