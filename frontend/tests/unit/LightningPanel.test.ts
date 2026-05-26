import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import LightningPanel from '$lib/panels/LightningPanel.svelte';

describe('LightningPanel', () => {
  it('shows no-strikes copy when past_24h=0', () => {
    render(LightningPanel, { props: { past_24h: 0 } });
    expect(screen.getByText('No strikes in the last 24h.')).toBeTruthy();
  });
});
