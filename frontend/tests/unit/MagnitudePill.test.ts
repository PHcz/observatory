import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import MagnitudePill from '$lib/atoms/MagnitudePill.svelte';

describe('MagnitudePill', () => {
  it('has class mag-small and text "2.5" for magnitude 2.5', () => {
    const { container } = render(MagnitudePill, { props: { magnitude: 2.5 } });
    expect(container.firstChild).toHaveClass('mag-small');
    expect((container.firstChild as HTMLElement).textContent?.trim()).toBe('2.5');
  });

  it('has class mag-mod and text "5.0" for magnitude 5.0', () => {
    const { container } = render(MagnitudePill, { props: { magnitude: 5.0 } });
    expect(container.firstChild).toHaveClass('mag-mod');
    expect((container.firstChild as HTMLElement).textContent?.trim()).toBe('5.0');
  });

  it('has class mag-big and text "6.5" for magnitude 6.5', () => {
    const { container } = render(MagnitudePill, { props: { magnitude: 6.5 } });
    expect(container.firstChild).toHaveClass('mag-big');
    expect((container.firstChild as HTMLElement).textContent?.trim()).toBe('6.5');
  });

  it('shows em-dash and mag-small class for null magnitude', () => {
    const { container } = render(MagnitudePill, { props: { magnitude: null } });
    expect(container.firstChild).toHaveClass('mag-small');
    expect((container.firstChild as HTMLElement).textContent?.trim()).toBe('—');
  });
});
