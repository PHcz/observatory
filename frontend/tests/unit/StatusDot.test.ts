import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import StatusDot from '$lib/atoms/StatusDot.svelte';

describe('StatusDot', () => {
  it('renders with class status-green for status=green', () => {
    const { container } = render(StatusDot, { props: { status: 'green' } });
    const dot = container.querySelector('.status-green');
    expect(dot).toBeTruthy();
  });

  it('renders with class status-yellow for status=yellow', () => {
    const { container } = render(StatusDot, { props: { status: 'yellow' } });
    const dot = container.querySelector('.status-yellow');
    expect(dot).toBeTruthy();
  });

  it('renders with class status-amber for status=amber', () => {
    const { container } = render(StatusDot, { props: { status: 'amber' } });
    const dot = container.querySelector('.status-amber');
    expect(dot).toBeTruthy();
  });

  it('renders with class status-red for status=red', () => {
    const { container } = render(StatusDot, { props: { status: 'red' } });
    const dot = container.querySelector('.status-red');
    expect(dot).toBeTruthy();
  });

  it('renders a span element', () => {
    const { container } = render(StatusDot, { props: { status: 'green' } });
    const span = container.querySelector('span.status-dot');
    expect(span).toBeTruthy();
  });
});
