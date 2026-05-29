// Settings store — Phase 8.5 UI-16.
// Persists to localStorage key observatory.settings.v1 with a 100 ms debounced write.

import { writable } from 'svelte/store';
import { parseSettings, DEFAULTS, type Settings } from '$lib/utils/settingsSchema';

const KEY = 'observatory.settings.v1';

function readInitial(): Settings {
  if (typeof localStorage === 'undefined') return structuredClone(DEFAULTS);
  try {
    return parseSettings(localStorage.getItem(KEY));
  } catch {
    return structuredClone(DEFAULTS);
  }
}

const inner = writable<Settings>(readInitial());
const { subscribe, set: innerSet, update: innerUpdate } = inner;

let writeTimer: ReturnType<typeof setTimeout> | null = null;
function scheduleWrite(value: Settings) {
  if (typeof localStorage === 'undefined') return;
  if (writeTimer) clearTimeout(writeTimer);
  writeTimer = setTimeout(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(value));
    } catch {
      // Private mode / quota — fail silently; UI shows hint per UI-SPEC.
    }
  }, 100);
}

export const settingsStore = {
  subscribe,
  set: (v: Settings) => {
    innerSet(v);
    scheduleWrite(v);
  },
  update: (fn: (v: Settings) => Settings) => {
    innerUpdate((v) => {
      const next = fn(v);
      scheduleWrite(next);
      return next;
    });
  },
  resetToDefaults: () => {
    const next = structuredClone(DEFAULTS);
    innerSet(next);
    scheduleWrite(next);
  },
};
