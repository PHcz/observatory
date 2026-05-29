// Theme store — Phase 8.5 UI-17.
// Derived from settingsStore.theme + system prefers-color-scheme.
// Single module-scope matchMedia listener; subscription applies data-theme to <html>.

import { derived, writable, type Readable } from 'svelte/store';
import { settingsStore } from './settings';

const systemPrefersDark = writable(false);

if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
  const mql = window.matchMedia('(prefers-color-scheme: dark)');
  systemPrefersDark.set(mql.matches);
  // matchMedia change event — modern API.
  mql.addEventListener('change', (e) => systemPrefersDark.set(e.matches));
}

export const themeStore: Readable<'light' | 'dark'> = derived(
  [settingsStore, systemPrefersDark],
  ([$settings, $sysDark]) => {
    if ($settings.theme === 'light') return 'light';
    if ($settings.theme === 'dark') return 'dark';
    return $sysDark ? 'dark' : 'light';
  }
);

// Side-effect: apply data-theme on <html> on every resolved-theme change.
if (typeof document !== 'undefined') {
  themeStore.subscribe((resolved) => {
    document.documentElement.dataset.theme = resolved;
  });
}
