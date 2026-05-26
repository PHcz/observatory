import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import HeaderPanel from '$lib/panels/HeaderPanel.svelte';

describe('HeaderPanel', () => {
  it('shows em-dash as hero placeholder when no data', () => {
    const { getByRole } = render(HeaderPanel);
    const hero = getByRole('heading', { level: 1 });
    expect(hero.textContent).toBe('—');
  });
});
