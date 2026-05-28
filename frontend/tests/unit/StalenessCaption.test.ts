import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import StalenessCaption from '$lib/atoms/StalenessCaption.svelte';

describe('StalenessCaption visibility (UI-14)', () => {
  it('hides entirely when level=fresh', () => {
    const { container } = render(StalenessCaption, { props: { lastTs: 1716908400, level: 'fresh' } });
    expect(container.querySelector('.staleness')).toBeNull();
  });
  it('shows when amber', () => {
    const { container } = render(StalenessCaption, { props: { lastTs: 1716908400, level: 'amber' } });
    expect(container.querySelector('.staleness')).not.toBeNull();
  });
  it('shows when red', () => {
    const { container } = render(StalenessCaption, { props: { lastTs: 1716908400, level: 'red' } });
    expect(container.querySelector('.staleness')).not.toBeNull();
  });
  it('hides when lastTs is null regardless of level', () => {
    const { container } = render(StalenessCaption, { props: { lastTs: null, level: 'amber' } });
    expect(container.querySelector('.staleness')).toBeNull();
  });
});
