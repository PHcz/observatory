import '@testing-library/jest-dom/vitest';

// jsdom in this project ships a partial localStorage shim (Phase 8.5 deviation Rule 3).
// Polyfill a complete in-memory Storage so tests in settings.store/theme.store can
// exercise clear/getItem/setItem cleanly. Idempotent (only installs once).
if (typeof window !== 'undefined' && typeof (window.localStorage as Storage | undefined)?.clear !== 'function') {
  const memoryStorage = (): Storage => {
    let store: Record<string, string> = {};
    return {
      get length() {
        return Object.keys(store).length;
      },
      clear: () => {
        store = {};
      },
      getItem: (key: string) => (key in store ? store[key] : null),
      setItem: (key: string, value: string) => {
        store[key] = String(value);
      },
      removeItem: (key: string) => {
        delete store[key];
      },
      key: (index: number) => Object.keys(store)[index] ?? null,
    };
  };
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    writable: true,
    value: memoryStorage(),
  });
  Object.defineProperty(window, 'sessionStorage', {
    configurable: true,
    writable: true,
    value: memoryStorage(),
  });
}
