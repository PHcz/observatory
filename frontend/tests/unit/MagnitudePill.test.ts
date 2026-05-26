import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import MagnitudePill from '$lib/atoms/MagnitudePill.svelte';

describe('MagnitudePill', () => {
  it('has class mag-small for magnitude 2.5', () => {
    const { container } = render(MagnitudePill, { props: { magnitude: 2.5 } });
    expect(container.firstChild).toHaveClass('mag-small');
  });
  it('has class mag-mod for magnitude 5.0', () => {
    const { container } = render(MagnitudePill, { props: { magnitude: 5.0 } });
    expect(container.firstChild).toHaveClass('mag-mod');
  });
  it('has class mag-big for magnitude 6.5', () => {
    const { container } = render(MagnitudePill, { props: { magnitude: 6.5 } });
    expect(container.firstChild).toHaveClass('mag-big');
  });
});
