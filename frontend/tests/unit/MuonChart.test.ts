import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import MuonChart from '$lib/panels/MuonChart.svelte';

describe('MuonChart', () => {
  it('renders a div with data-chart="muon"', () => {
    const { container } = render(MuonChart);
    expect(container.querySelector('[data-chart="muon"]')).toBeTruthy();
  });
});
