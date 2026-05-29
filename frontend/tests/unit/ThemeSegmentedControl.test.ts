import { describe, it, expect, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import { get } from 'svelte/store';
import ThemeSegmentedControl from '$lib/components/ThemeSegmentedControl.svelte';
import { settingsStore } from '$lib/stores/settings';

describe('ThemeSegmentedControl (UI-17)', () => {
  beforeEach(() => {
    settingsStore.resetToDefaults();
  });

  it('renders 3 radio inputs with values light, dark, auto and a fieldset + visually-hidden legend', () => {
    const { container } = render(ThemeSegmentedControl);
    const fieldset = container.querySelector('fieldset');
    expect(fieldset).not.toBeNull();
    const legend = container.querySelector('legend');
    expect(legend).not.toBeNull();
    expect(legend?.textContent?.trim()).toBe('Theme');
    expect(legend?.className).toContain('visually-hidden');
    const radios = container.querySelectorAll('input[type="radio"]');
    expect(radios.length).toBe(3);
    const values = Array.from(radios).map((r) => (r as HTMLInputElement).value);
    expect(values).toEqual(['light', 'dark', 'auto']);
  });

  it('initially checks the radio matching settingsStore.theme (default auto)', () => {
    const { container } = render(ThemeSegmentedControl);
    const checked = container.querySelector('input[type="radio"]:checked') as HTMLInputElement;
    expect(checked?.value).toBe('auto');
  });

  it('each radio has the exact aria-label per UI-SPEC Copywriting Contract', () => {
    const { container } = render(ThemeSegmentedControl);
    const radios = Array.from(container.querySelectorAll('input[type="radio"]')) as HTMLInputElement[];
    const labels = radios.map((r) => r.getAttribute('aria-label'));
    expect(labels).toEqual([
      'Light theme',
      'Dark theme',
      'Automatic theme (follow system)',
    ]);
  });

  it('clicking the Dark radio updates settingsStore theme to dark', async () => {
    const { container } = render(ThemeSegmentedControl);
    const darkRadio = container.querySelector('input[value="dark"]') as HTMLInputElement;
    await fireEvent.click(darkRadio);
    expect(get(settingsStore).theme).toBe('dark');
  });

  it('selected segment has .selected class on the label', async () => {
    const { container } = render(ThemeSegmentedControl);
    settingsStore.update((s) => ({ ...s, theme: 'dark' }));
    // Force re-render via subscription tick
    await Promise.resolve();
    const labels = container.querySelectorAll('label.seg');
    // Default auto means third label is selected, change makes second selected.
    // Find label wrapping checked radio
    const checkedRadio = container.querySelector('input[type="radio"]:checked') as HTMLInputElement;
    const parentLabel = checkedRadio?.closest('label');
    expect(parentLabel?.classList.contains('selected')).toBe(true);
  });
});
