import { describe, it, expect, beforeEach } from 'vitest';
import { render } from '@testing-library/svelte';
import { tick } from 'svelte';
import CadenceWarningBanner from '$lib/components/CadenceWarningBanner.svelte';
import { healthStore } from '$lib/stores/health';
import type { HealthResponse, SourceHealth } from '$lib/types';

function mkEntry(
  cadence_warning: boolean,
  last_event_ts: number | null = null,
): SourceHealth {
  return {
    last_event_ts,
    freshness: 'healthy',
    staleness_threshold_sec: 1800,
    last_poll_status: null,
    cadence_warning,
  } as SourceHealth & { cadence_warning: boolean };
}

function mkHealth(overrides: Partial<HealthResponse['local']>): HealthResponse {
  const base = {
    weather: mkEntry(false),
    muon: mkEntry(false),
  } as HealthResponse['local'];
  return {
    timestamp: 0,
    status: 'healthy',
    local: { ...base, ...overrides },
    external: {
      usgs: mkEntry(false),
      emsc: mkEntry(false),
      bgs: mkEntry(false),
      noaa: mkEntry(false),
      blitzortung: mkEntry(false),
      aurora: mkEntry(false),
    } as HealthResponse['external'],
    pi: { temp_c: null, throttled: null, status: 'healthy', warnings: [] },
  };
}

describe('CadenceWarningBanner (UI-20)', () => {
  beforeEach(() => {
    sessionStorage.clear();
    healthStore.set({ data: null, lastFetchTs: null });
  });

  it('renders when weather cadence_warning=true', async () => {
    healthStore.set({
      data: mkHealth({ weather: mkEntry(true, Math.floor(Date.now() / 1000) - 3600) }),
      lastFetchTs: 0,
    });
    const { container } = render(CadenceWarningBanner);
    await tick();
    expect(container.querySelector('.banner')).not.toBeNull();
    expect(container.querySelector('.label')?.textContent).toContain('WEATHER NODE');
  });

  it('does not render when all sources fresh', async () => {
    healthStore.set({ data: mkHealth({}), lastFetchTs: 0 });
    const { container } = render(CadenceWarningBanner);
    await tick();
    expect(container.querySelector('.banner')).toBeNull();
  });

  it('dismiss writes sessionStorage; banner hides', async () => {
    healthStore.set({
      data: mkHealth({ weather: mkEntry(true, Math.floor(Date.now() / 1000) - 3600) }),
      lastFetchTs: 0,
    });
    const { container } = render(CadenceWarningBanner);
    await tick();
    const btn = container.querySelector('.dismiss') as HTMLButtonElement;
    expect(btn).not.toBeNull();
    btn.click();
    await tick();
    expect(sessionStorage.getItem('cadence-dismissed-weather')).toBe('1');
    expect(container.querySelector('.banner')).toBeNull();
  });

  it('auto-clears dismissed state when condition resolves', async () => {
    sessionStorage.setItem('cadence-dismissed-weather', '1');
    healthStore.set({ data: mkHealth({}), lastFetchTs: 0 });
    render(CadenceWarningBanner);
    await tick();
    expect(sessionStorage.getItem('cadence-dismissed-weather')).toBeNull();
  });

  it('renders no emoji characters in output', async () => {
    healthStore.set({
      data: mkHealth({ weather: mkEntry(true, Math.floor(Date.now() / 1000) - 3600) }),
      lastFetchTs: 0,
    });
    const { container } = render(CadenceWarningBanner);
    await tick();
    const text = container.textContent ?? '';
    // High-surrogate emoji range
    expect(/[\u{1F300}-\u{1FAFF}]/u.test(text)).toBe(false);
  });
});
