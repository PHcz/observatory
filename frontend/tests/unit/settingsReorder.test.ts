import { describe, it, expect, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/svelte';
import { get } from 'svelte/store';
import SettingsPage from '../../src/routes/settings/+page.svelte';
import { settingsStore } from '$lib/stores/settings';
import { ALL_PANELS } from '$lib/utils/settingsSchema';

describe('settings reorder wiring', () => {
  beforeEach(() => settingsStore.resetToDefaults());

  it('clicking the second row up-button swaps the first two panels in order', async () => {
    const { getAllByLabelText } = render(SettingsPage);
    const before = get(settingsStore).order;
    // Second row corresponds to ALL_PANELS[1]; its "up" moves it to index 0.
    const upButtons = getAllByLabelText(/Move .* up/);
    await fireEvent.click(upButtons[1]);
    const after = get(settingsStore).order;
    expect(after[0]).toBe(before[1]);
    expect(after[1]).toBe(before[0]);
    expect(new Set(after)).toEqual(new Set(ALL_PANELS));
  });
});
