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
let pendingValue: Settings | null = null;

function flushWrite() {
  if (typeof localStorage === 'undefined' || pendingValue == null) return;
  try {
    localStorage.setItem(KEY, JSON.stringify(pendingValue));
  } catch {
    // Private mode / quota — fail silently; UI shows hint per UI-SPEC.
  }
  pendingValue = null;
  if (writeTimer) {
    clearTimeout(writeTimer);
    writeTimer = null;
  }
}

function scheduleWrite(value: Settings) {
  if (typeof localStorage === 'undefined') return;
  pendingValue = value;
  if (writeTimer) clearTimeout(writeTimer);
  writeTimer = setTimeout(flushWrite, 100);
}

// Flush any pending debounced write before the page unloads so reloads/closes
// never lose a setting change. Without this guard, fast user actions
// (toggle + reload) drop the change because the 100ms timer never fires.
if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', flushWrite);
  window.addEventListener('beforeunload', flushWrite);
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
