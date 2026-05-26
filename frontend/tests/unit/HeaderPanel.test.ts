import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import HeaderPanel from '$lib/panels/HeaderPanel.svelte';
import { weatherStore } from '$lib/stores/weather';
import type { WeatherData } from '$lib/types';

describe('HeaderPanel', () => {
  it('shows em-dash as hero placeholder when no data', () => {
    weatherStore.set({ current: null, history: [], lastUpdateTs: null });
    const { getByRole } = render(HeaderPanel);
    const hero = getByRole('heading', { level: 1 });
    expect(hero.textContent).toContain('—');
  });

  it('shows temperature when weatherStore has data', async () => {
    weatherStore.set({ current: null, history: [], lastUpdateTs: null });
    render(HeaderPanel);
    const weatherData: WeatherData = { ts: 1000000, temp_c: 14.2, humidity_pct: 65, pressure_hpa: 1013, lux: 500 };
    weatherStore.set({ current: weatherData, history: [], lastUpdateTs: 1000000 });
    await tick();
    expect(screen.getByText('14.2')).toBeTruthy();
  });

  it('renders hero-overline with "Outside · Right now"', () => {
    weatherStore.set({ current: null, history: [], lastUpdateTs: null });
    render(HeaderPanel);
    expect(screen.getByText('Outside · Right now')).toBeTruthy();
  });

  it('renders aside labels (Local time, Sun, Moon)', () => {
    weatherStore.set({ current: null, history: [], lastUpdateTs: null });
    render(HeaderPanel);
    expect(screen.getByText('Local time')).toBeTruthy();
    expect(screen.getByText('Sun')).toBeTruthy();
    expect(screen.getByText('Moon')).toBeTruthy();
  });

  it('renders subtitle text', () => {
    weatherStore.set({ current: null, history: [], lastUpdateTs: null });
    render(HeaderPanel);
    // Subtitle should contain a time descriptor
    const subtitleEl = document.querySelector('.subtitle');
    expect(subtitleEl).toBeTruthy();
    const text = subtitleEl?.textContent ?? '';
    expect(text.length).toBeGreaterThan(0);
    expect(text).not.toContain('null');
    expect(text).not.toContain('undefined');
  });
});
