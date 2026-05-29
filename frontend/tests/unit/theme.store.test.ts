import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';

// Mutable matchMedia mock — we control matches + change listeners per test.
type Listener = (e: { matches: boolean }) => void;
let mqlMatches = false;
let mqlListeners: Listener[] = [];

function installMatchMedia() {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation(() => ({
      get matches() {
        return mqlMatches;
      },
      media: '(prefers-color-scheme: dark)',
      addEventListener: (_e: string, cb: Listener) => mqlListeners.push(cb),
      removeEventListener: (_e: string, cb: Listener) => {
        mqlListeners = mqlListeners.filter((l) => l !== cb);
      },
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    })),
  });
}

function fireMatchMediaChange(matches: boolean) {
  mqlMatches = matches;
  for (const l of mqlListeners) l({ matches });
}

describe('themeStore', () => {
  beforeEach(async () => {
    mqlMatches = false;
    mqlListeners = [];
    installMatchMedia();
    localStorage.clear();
    document.documentElement.dataset.theme = '';
    vi.resetModules();
  });

  it("yields 'light' when settingsStore.theme==='light' regardless of system", async () => {
    mqlMatches = true; // system would prefer dark
    installMatchMedia();
    const { settingsStore } = await import('$lib/stores/settings');
    const { themeStore } = await import('$lib/stores/theme');
    settingsStore.update((s) => ({ ...s, theme: 'light' }));
    expect(get(themeStore)).toBe('light');
  });

  it("yields 'dark' when settingsStore.theme==='dark' regardless of system", async () => {
    mqlMatches = false;
    installMatchMedia();
    const { settingsStore } = await import('$lib/stores/settings');
    const { themeStore } = await import('$lib/stores/theme');
    settingsStore.update((s) => ({ ...s, theme: 'dark' }));
    expect(get(themeStore)).toBe('dark');
  });

  it("auto + system dark resolves to 'dark'", async () => {
    mqlMatches = true;
    installMatchMedia();
    const { settingsStore } = await import('$lib/stores/settings');
    const { themeStore } = await import('$lib/stores/theme');
    settingsStore.update((s) => ({ ...s, theme: 'auto' }));
    expect(get(themeStore)).toBe('dark');
  });

  it("auto + system light resolves to 'light'", async () => {
    mqlMatches = false;
    installMatchMedia();
    const { settingsStore } = await import('$lib/stores/settings');
    const { themeStore } = await import('$lib/stores/theme');
    settingsStore.update((s) => ({ ...s, theme: 'auto' }));
    expect(get(themeStore)).toBe('light');
  });

  it('applies data-theme to <html> on resolved-theme change', async () => {
    mqlMatches = false;
    installMatchMedia();
    const { settingsStore } = await import('$lib/stores/settings');
    await import('$lib/stores/theme');
    settingsStore.update((s) => ({ ...s, theme: 'dark' }));
    expect(document.documentElement.dataset.theme).toBe('dark');
    settingsStore.update((s) => ({ ...s, theme: 'light' }));
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it("auto + matchMedia change flips to dark when system flips", async () => {
    mqlMatches = false;
    installMatchMedia();
    const { settingsStore } = await import('$lib/stores/settings');
    const { themeStore } = await import('$lib/stores/theme');
    settingsStore.update((s) => ({ ...s, theme: 'auto' }));
    expect(get(themeStore)).toBe('light');
    fireMatchMediaChange(true);
    expect(get(themeStore)).toBe('dark');
  });
});
