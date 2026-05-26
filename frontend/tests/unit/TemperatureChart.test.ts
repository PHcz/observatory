import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import TemperatureChart from '$lib/panels/TemperatureChart.svelte';

describe('TemperatureChart', () => {
  it('renders a div with data-chart="temperature"', () => {
    const { container } = render(TemperatureChart);
    expect(container.querySelector('[data-chart="temperature"]')).toBeTruthy();
  });
});
