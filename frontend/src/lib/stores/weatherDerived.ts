import { writable, type Writable } from 'svelte/store';
import type { WeatherTodayResponse, WeatherOutlookResponse } from '$lib/types';
import { fetchWeatherToday, fetchWeatherOutlook } from '$lib/api/rest';

export interface WeatherDerivedState {
  today: WeatherTodayResponse | null;
  outlook: WeatherOutlookResponse | null;
}

export const weatherDerivedStore: Writable<WeatherDerivedState> = writable({
  today: null,
  outlook: null,
});

// today-so-far: 5-minute poll (conditions change throughout the day)
// outlook: 15-minute poll (Zambretti needs ~3h pressure history; no need to rush)
const TODAY_POLL_MS = 5 * 60 * 1000;
const OUTLOOK_POLL_MS = 15 * 60 * 1000;

let todayTimer: ReturnType<typeof setInterval> | null = null;
let outlookTimer: ReturnType<typeof setInterval> | null = null;

async function pollToday(): Promise<void> {
  try {
    const today = await fetchWeatherToday();
    weatherDerivedStore.update((s) => ({ ...s, today }));
  } catch {
    // Swallow — strip shows empty state on fetch failure.
  }
}

async function pollOutlook(): Promise<void> {
  try {
    const outlook = await fetchWeatherOutlook();
    weatherDerivedStore.update((s) => ({ ...s, outlook }));
  } catch {
    // Swallow — card shows empty state on fetch failure.
  }
}

export function initWeatherDerivedPolling(): () => void {
  void pollToday();
  void pollOutlook();

  todayTimer = setInterval(() => { void pollToday(); }, TODAY_POLL_MS);
  outlookTimer = setInterval(() => { void pollOutlook(); }, OUTLOOK_POLL_MS);

  return () => {
    if (todayTimer) { clearInterval(todayTimer); todayTimer = null; }
    if (outlookTimer) { clearInterval(outlookTimer); outlookTimer = null; }
  };
}
