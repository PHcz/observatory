import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import AuroraPanel from '$lib/panels/AuroraPanel.svelte';

describe('AuroraPanel', () => {
  it('dot has class containing green for status=green', () => {
    const { container } = render(AuroraPanel, { props: { status: 'green' } });
    const dot = container.querySelector('[class*="green"]');
    expect(dot).toBeTruthy();
  });
  it('dot has class containing red for status=red', () => {
    const { container } = render(AuroraPanel, { props: { status: 'red' } });
    const dot = container.querySelector('[class*="red"]');
    expect(dot).toBeTruthy();
  });
});
