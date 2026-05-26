import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import StatsRow from '$lib/panels/StatsRow.svelte';

describe('StatsRow', () => {
  it('renders four em-dashes when weather data is null', () => {
    const { getAllByText } = render(StatsRow);
    const dashes = getAllByText('—');
    expect(dashes.length).toBeGreaterThanOrEqual(4);
  });
});
