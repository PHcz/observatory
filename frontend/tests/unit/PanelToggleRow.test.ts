import { describe, it, expect, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import { get } from 'svelte/store';
import PanelToggleRow from '$lib/components/PanelToggleRow.svelte';
import { settingsStore } from '$lib/stores/settings';

describe('PanelToggleRow (UI-16)', () => {
  beforeEach(() => {
    settingsStore.resetToDefaults();
  });

  it('renders a label containing label span and input[type=checkbox][role=switch]', () => {
    const { container } = render(PanelToggleRow, { props: { panelKey: 'lightning', label: 'Lightning' } });
    const label = container.querySelector('label');
    expect(label).not.toBeNull();
    const labelSpan = container.querySelector('span.label');
    expect(labelSpan?.textContent?.trim()).toBe('Lightning');
    const input = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(input).not.toBeNull();
    expect(input.getAttribute('role')).toBe('switch');
  });

  it('aria-label is "Show {label} panel" constructed from prop', () => {
    const { container } = render(PanelToggleRow, { props: { panelKey: 'lightning', label: 'Lightning' } });
    const input = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(input.getAttribute('aria-label')).toBe('Show Lightning panel');
  });

  it('checked reflects $settingsStore.panels[panelKey] (default true)', () => {
    const { container } = render(PanelToggleRow, { props: { panelKey: 'lightning', label: 'Lightning' } });
    const input = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(input.checked).toBe(true);
  });

  it('clicking the checkbox toggles settingsStore.panels[panelKey]', async () => {
    const { container } = render(PanelToggleRow, { props: { panelKey: 'lightning', label: 'Lightning' } });
    const input = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    await fireEvent.click(input);
    expect(get(settingsStore).panels.lightning).toBe(false);
  });

  it('disabled prop propagates to input', () => {
    const { container } = render(PanelToggleRow, {
      props: { panelKey: 'lightning', label: 'Lightning', disabled: true },
    });
    const input = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(input.disabled).toBe(true);
  });
});
